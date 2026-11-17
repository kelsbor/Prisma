package br.com.prisma.financas.domain.category

import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.CategorySource
import br.com.prisma.financas.domain.model.PluggyCategories

/**
 * Categoria da transação = categoria da Pluggy, sem regras locais.
 * Nome: o português do catálogo da Pluggy (descriptionTranslated). Se o id não estiver
 * no catálogo, usa o nome que veio na transação (em inglês).
 * Exceção: se o usuário trocou a categoria manualmente, vale a escolha dele.
 *
 * @param catalog id da categoria → nome em português (catálogo GET /categories).
 */
class CategoryResolver(private val catalog: Map<String, String>) {

    data class Resolved(val category: Category, val source: CategorySource)

    fun category(id: String?, fallbackName: String? = null): Category {
        val cid = id?.trim().orEmpty()
        return PluggyCategories.build(cid, catalog[cid] ?: fallbackName)
    }

    fun resolve(pluggyCategoryId: String?, pluggyCategoryName: String?, overrideCategoryId: String?): Resolved {
        if (!overrideCategoryId.isNullOrBlank() && overrideCategoryId in catalog) {
            return Resolved(category(overrideCategoryId), CategorySource.MANUAL)
        }
        if (pluggyCategoryId.isNullOrBlank()) return Resolved(PluggyCategories.UNCATEGORIZED, CategorySource.DEFAULT)
        return Resolved(category(pluggyCategoryId, pluggyCategoryName), CategorySource.PLUGGY)
    }
}
