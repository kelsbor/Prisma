package br.com.prisma.financas.domain.model

import br.com.prisma.financas.core.money.Money
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BankNamesTest {
    private fun acc(type: AccountType, name: String) = SourceAccount(
        id = name, itemId = "it", type = type, subtype = null, name = name, number = null,
        balance = Money.ZERO, currencyCode = "BRL", creditLimit = null, availableLimit = null, dueDate = null,
    )

    @Test fun `conexao direta usa o nome do conector`() {
        assertEquals("Banco Teste", BankNames.infer("Banco Teste", listOf(acc(AccountType.BANK, "Conta X - Y"))))
    }

    @Test fun `meu pluggy usa o nome da conta bancaria ate o traco`() {
        val accounts = listOf(acc(AccountType.CREDIT, "platinum"), acc(AccountType.BANK, "Banco Fictício S.A. - Instituição de Pagamento"))
        assertEquals("Banco Fictício S.A.", BankNames.infer("MeuPluggy", accounts))
    }

    @Test fun `meu pluggy so com cartao fica sem nome`() {
        assertNull(BankNames.infer("MeuPluggy", listOf(acc(AccountType.CREDIT, "platinum"))))
    }
}
