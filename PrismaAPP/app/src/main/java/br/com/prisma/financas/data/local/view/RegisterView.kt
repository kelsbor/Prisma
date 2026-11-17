package br.com.prisma.financas.data.local.view

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.DatabaseView
import androidx.room.Query

/**
 * vw_registers: uma linha por transação, pronta para leitura (e para o agente text-to-SQL).
 * Junta transaction_fact + account_dim + item_dim + category_dim + category_override,
 * com as MESMAS regras das telas:
 * - categoria: a escolhida manualmente; senão a da Pluggy em português; sem id → "Sem categoria";
 * - tipo: transferencia (fatura 05100000, mesma titularidade 04…, investimentos 03…),
 *   gasto (valor < 0), estorno (valor > 0 no cartão), entrada (valor > 0 na conta);
 * - valor_gasto / valor_entrada: o quanto a linha soma nos totais (estorno abate o gasto).
 *
 * Valores: valor_centavos é exato (inteiro); valor, valor_gasto e valor_entrada estão em reais.
 */
@DatabaseView(viewName = RegisterView.NAME, value = RegisterView.SQL)
data class RegisterView(
    @ColumnInfo(name = "transacao_id") val transacaoId: String,
    @ColumnInfo(name = "data") val data: String,
    @ColumnInfo(name = "ano") val ano: Int,
    @ColumnInfo(name = "mes") val mes: Int,
    @ColumnInfo(name = "descricao") val descricao: String,
    @ColumnInfo(name = "estabelecimento") val estabelecimento: String?,
    @ColumnInfo(name = "valor_centavos") val valorCentavos: Long,
    @ColumnInfo(name = "valor") val valor: Double,
    @ColumnInfo(name = "categoria_id") val categoriaId: String?,
    @ColumnInfo(name = "categoria") val categoria: String,
    @ColumnInfo(name = "categoria_manual") val categoriaManual: Boolean,
    @ColumnInfo(name = "grupo_categoria") val grupoCategoria: String?,
    @ColumnInfo(name = "tipo") val tipo: String,
    @ColumnInfo(name = "valor_gasto") val valorGasto: Double,
    @ColumnInfo(name = "valor_entrada") val valorEntrada: Double,
    @ColumnInfo(name = "conta") val conta: String?,
    @ColumnInfo(name = "tipo_conta") val tipoConta: String,
    @ColumnInfo(name = "banco") val banco: String?,
    @ColumnInfo(name = "pendente") val pendente: Boolean,
    @ColumnInfo(name = "parcela") val parcela: Int?,
    @ColumnInfo(name = "total_parcelas") val totalParcelas: Int?,
) {
    companion object {
        const val NAME = "vw_registers"

        const val SQL =
            "SELECT " +
                "r.id AS transacao_id, " +
                "date(r.dateEpochDay * 86400, 'unixepoch') AS data, " +
                "CAST(strftime('%Y', r.dateEpochDay * 86400, 'unixepoch') AS INTEGER) AS ano, " +
                "CAST(strftime('%m', r.dateEpochDay * 86400, 'unixepoch') AS INTEGER) AS mes, " +
                "r.description AS descricao, " +
                "r.merchantName AS estabelecimento, " +
                "r.amountCents AS valor_centavos, " +
                "r.amountCents / 100.0 AS valor, " +
                "r.categoria_id AS categoria_id, " +
                "CASE WHEN COALESCE(r.categoria_id, '') = '' THEN 'Sem categoria' " +
                "ELSE COALESCE(c.name, r.pluggyCategory, 'Sem categoria') END AS categoria, " +
                "r.manual AS categoria_manual, " +
                "g.name AS grupo_categoria, " +
                "CASE WHEN r.transferencia = 1 THEN 'transferencia' " +
                "WHEN r.amountCents < 0 THEN 'gasto' " +
                "WHEN r.amountCents > 0 AND r.tipo_conta = 'cartao' THEN 'estorno' " +
                "WHEN r.amountCents > 0 THEN 'entrada' " +
                "ELSE 'neutro' END AS tipo, " +
                "CASE WHEN r.transferencia = 1 THEN 0 " +
                "WHEN r.amountCents < 0 OR r.tipo_conta = 'cartao' THEN -r.amountCents / 100.0 " +
                "ELSE 0 END AS valor_gasto, " +
                "CASE WHEN r.transferencia = 0 AND r.amountCents > 0 AND r.tipo_conta = 'conta' " +
                "THEN r.amountCents / 100.0 ELSE 0 END AS valor_entrada, " +
                "r.conta AS conta, " +
                "r.tipo_conta AS tipo_conta, " +
                "r.banco AS banco, " +
                "CASE WHEN r.status = 'PENDING' THEN 1 ELSE 0 END AS pendente, " +
                "r.installmentNumber AS parcela, " +
                "r.totalInstallments AS total_parcelas " +
                "FROM (" +
                "SELECT t.*, " +
                "COALESCE(oc.id, t.pluggyCategoryId) AS categoria_id, " +
                "CASE WHEN oc.id IS NOT NULL THEN 1 ELSE 0 END AS manual, " +
                "CASE WHEN COALESCE(oc.id, t.pluggyCategoryId, '') = '05100000' " +
                "OR substr(COALESCE(oc.id, t.pluggyCategoryId, ''), 1, 2) IN ('03', '04') " +
                "THEN 1 ELSE 0 END AS transferencia, " +
                "CASE WHEN a.type = 'CREDIT' THEN 'cartao' ELSE 'conta' END AS tipo_conta, " +
                "a.name AS conta, " +
                "COALESCE(i.bankName, i.connectorName) AS banco " +
                "FROM transaction_fact t " +
                "LEFT JOIN account_dim a ON a.id = t.accountId " +
                "LEFT JOIN item_dim i ON i.id = a.itemId " +
                "LEFT JOIN category_override o ON o.transactionId = t.id " +
                "LEFT JOIN category_dim oc ON oc.id = o.categoryId" +
                ") r " +
                "LEFT JOIN category_dim c ON c.id = r.categoria_id " +
                "LEFT JOIN category_dim g ON g.id = substr(r.categoria_id, 1, 2) || '000000'"
    }
}

@Dao
interface RegisterDao {
    @Query("SELECT * FROM vw_registers ORDER BY data DESC, transacao_id ASC")
    suspend fun all(): List<RegisterView>
}
