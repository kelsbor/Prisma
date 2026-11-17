package br.com.prisma.financas.domain.model

/** EXPENSE/INCOME orientam a exibição; TRANSFER fica fora de gastos e entradas (evita contar duas vezes). */
enum class CategoryKind { EXPENSE, INCOME, TRANSFER }

/** Categoria da Pluggy, exatamente como no catálogo dela (id + nome em português). */
data class Category(
    val id: String,
    val name: String,
    val iconKey: String,
    val colorArgb: Long,
    val kind: CategoryKind,
)

/** Item do catálogo GET /categories. [name] = descriptionTranslated (português); [originalName] = description. */
data class SourceCategory(val id: String, val name: String, val originalName: String?)

/**
 * Monta a [Category] a partir do id/nome da Pluggy, sem renomear nem reagrupar.
 * Só acrescenta ícone e cor pelo grupo (2 primeiros dígitos do id) e o tipo usado nos totais.
 */
object PluggyCategories {
    const val UNCATEGORIZED_ID = ""
    val UNCATEGORIZED = Category(UNCATEGORIZED_ID, "Sem categoria", "more", 0xFF94A3B8, CategoryKind.EXPENSE)

    const val CREDIT_CARD_PAYMENT = "05100000"

    fun build(id: String?, name: String?): Category {
        val cid = id?.trim().orEmpty()
        if (cid.isEmpty()) return UNCATEGORIZED
        val (icon, color) = style(cid)
        return Category(cid, name?.takeIf { it.isNotBlank() } ?: "Sem categoria", icon, color, kind(cid))
    }

    /**
     * Fora dos totais de gasto/entrada: pagamento de fatura (a compra já foi contada no cartão),
     * transferências entre contas do mesmo titular e investimentos.
     */
    fun kind(id: String): CategoryKind = when {
        id == CREDIT_CARD_PAYMENT -> CategoryKind.TRANSFER
        id.startsWith("03") || id.startsWith("04") -> CategoryKind.TRANSFER
        id.startsWith("01") -> CategoryKind.INCOME
        else -> CategoryKind.EXPENSE
    }

    private fun style(id: String): Pair<String, Long> = when {
        id == CREDIT_CARD_PAYMENT -> "card" to 0xFF6B7280
        id.startsWith("1102") -> "delivery" to 0xFFD97706
        id.startsWith("0702") -> "school" to 0xFF0891B2
        id.startsWith("0703") -> "health" to 0xFFDC2626
        id.startsWith("0704") -> "celebration" to 0xFFEA580C
        else -> when (id.take(2)) {
            "01" -> "payments" to 0xFF059669
            "02" -> "percent" to 0xFFB91C1C
            "03" -> "trending" to 0xFF4F46E5
            "04" -> "sync" to 0xFF6B7280
            "05" -> "swap" to 0xFF0D9488
            "06", "15", "16" -> "bank" to 0xFF78716C
            "07" -> "receipt" to 0xFF64748B
            "08" -> "bag" to 0xFFDB2777
            "09" -> "subscriptions" to 0xFF9333EA
            "10" -> "cart" to 0xFF16A34A
            "11" -> "restaurant" to 0xFFE8743B
            "12" -> "flight" to 0xFF0284C7
            "14" -> "casino" to 0xFFBE123C
            "17" -> "home" to 0xFF7C3AED
            "18" -> "health" to 0xFFDC2626
            "19" -> "car" to 0xFF2563EB
            "20" -> "shield" to 0xFF475569
            "21" -> "celebration" to 0xFFEA580C
            else -> "more" to 0xFF94A3B8
        }
    }
}
