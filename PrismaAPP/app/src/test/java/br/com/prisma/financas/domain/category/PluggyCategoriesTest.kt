package br.com.prisma.financas.domain.category

import br.com.prisma.financas.domain.model.CategoryKind
import br.com.prisma.financas.domain.model.CategorySource
import br.com.prisma.financas.domain.model.PluggyCategories
import org.junit.Assert.assertEquals
import org.junit.Test

class PluggyCategoriesTest {
    // Trecho do catálogo real (id → descriptionTranslated)
    private val catalog = mapOf(
        "05100000" to "Pagamento de cartão de crédito",
        "11020000" to "Delivery de alimentos",
        "10000000" to "Supermercado",
        "200100000" to "Seguro de vida",
    )
    private val resolver = CategoryResolver(catalog)

    @Test fun `ingles da transacao vira o portugues do catalogo da Pluggy`() {
        val r = resolver.resolve("11020000", "Food delivery", null)
        assertEquals("Delivery de alimentos", r.category.name)
        assertEquals("11020000", r.category.id)
        assertEquals(CategorySource.PLUGGY, r.source)
    }

    @Test fun `id fora do catalogo mantem o nome original`() {
        assertEquals("Some new category", resolver.resolve("77000000", "Some new category", null).category.name)
    }

    @Test fun `sem categoria`() {
        val r = resolver.resolve(null, null, null)
        assertEquals(PluggyCategories.UNCATEGORIZED, r.category)
        assertEquals(CategorySource.DEFAULT, r.source)
    }

    @Test fun `escolha manual vence a da Pluggy`() {
        val r = resolver.resolve("11020000", "Food delivery", overrideCategoryId = "10000000")
        assertEquals("Supermercado", r.category.name)
        assertEquals(CategorySource.MANUAL, r.source)
    }

    @Test fun `escolha manual com id que nao existe no catalogo e ignorada`() {
        assertEquals(CategorySource.PLUGGY, resolver.resolve("10000000", "Groceries", "lazer").source)
    }

    @Test fun `tipos usados nos totais`() {
        assertEquals(CategoryKind.TRANSFER, PluggyCategories.kind("05100000")) // pagamento de fatura
        assertEquals(CategoryKind.TRANSFER, PluggyCategories.kind("04020000")) // mesma titularidade
        assertEquals(CategoryKind.TRANSFER, PluggyCategories.kind("03020000")) // investimento
        assertEquals(CategoryKind.INCOME, PluggyCategories.kind("01010000"))
        assertEquals(CategoryKind.EXPENSE, PluggyCategories.kind("05070000"))  // Pix para terceiros conta como gasto
        assertEquals(CategoryKind.EXPENSE, PluggyCategories.kind("200100000"))
    }
}
