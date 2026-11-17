package br.com.prisma.financas.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.Casino
import androidx.compose.material.icons.outlined.Celebration
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material.icons.outlined.DeliveryDining
import androidx.compose.material.icons.outlined.DirectionsCar
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Flight
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.LocalHospital
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.Percent
import androidx.compose.material.icons.outlined.Receipt
import androidx.compose.material.icons.outlined.Restaurant
import androidx.compose.material.icons.outlined.School
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material.icons.outlined.Subscriptions
import androidx.compose.material.icons.outlined.SwapHoriz
import androidx.compose.material.icons.outlined.SyncAlt
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.ItemHealth
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.ui.common.brl
import br.com.prisma.financas.ui.common.label
import br.com.prisma.financas.ui.theme.MoneyTextStyle
import br.com.prisma.financas.ui.theme.PrismaThemeExt

fun categoryIcon(iconKey: String): ImageVector = when (iconKey) {
    "restaurant" -> Icons.Outlined.Restaurant
    "delivery" -> Icons.Outlined.DeliveryDining
    "cart" -> Icons.Outlined.ShoppingCart
    "car" -> Icons.Outlined.DirectionsCar
    "home" -> Icons.Outlined.Home
    "health" -> Icons.Outlined.LocalHospital
    "school" -> Icons.Outlined.School
    "bag" -> Icons.Outlined.ShoppingBag
    "subscriptions" -> Icons.Outlined.Subscriptions
    "celebration" -> Icons.Outlined.Celebration
    "flight" -> Icons.Outlined.Flight
    "receipt" -> Icons.Outlined.Receipt
    "shield" -> Icons.Outlined.Shield
    "bank" -> Icons.Outlined.AccountBalance
    "percent" -> Icons.Outlined.Percent
    "casino" -> Icons.Outlined.Casino
    "swap" -> Icons.Outlined.SwapHoriz
    "payments" -> Icons.Outlined.Payments
    "trending" -> Icons.AutoMirrored.Outlined.TrendingUp
    "sync" -> Icons.Outlined.SyncAlt
    "card" -> Icons.Outlined.CreditCard
    else -> Icons.Outlined.MoreHoriz
}

@Composable
fun CategoryIcon(category: Category, size: Dp = 40.dp) {
    val color = Color(category.colorArgb)
    Box(
        Modifier.size(size).clip(CircleShape).background(color.copy(alpha = 0.16f)),
        contentAlignment = Alignment.Center,
    ) {
        Icon(categoryIcon(category.iconKey), contentDescription = null, tint = color, modifier = Modifier.size(size * 0.5f))
    }
}

/** Valor com cor semântica: entradas em verde, saídas na cor do texto (sem alarmismo). */
@Composable
fun AmountText(amount: Money, modifier: Modifier = Modifier, style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.bodyLarge) {
    Text(
        text = amount.brl(showPlus = amount.isPositive),
        style = style.merge(MoneyTextStyle),
        color = if (amount.isPositive) PrismaThemeExt.finance.income else MaterialTheme.colorScheme.onSurface,
        modifier = modifier,
        maxLines = 1,
    )
}

@Composable
fun TransactionRow(tx: TransactionView, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CategoryIcon(tx.category)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(tx.description, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val installment = if ((tx.totalInstallments ?: 0) > 1) " · ${tx.installmentNumber}/${tx.totalInstallments}" else ""
            Text(
                "${tx.category.name} · ${tx.accountName}$installment",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(horizontalAlignment = Alignment.End) {
            AmountText(tx.amount)
            if (tx.isPending) {
                Text("Pendente", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.tertiary)
            }
        }
    }
}

/** Faixa de aviso (erro de sincronização, autorização expirando etc.). */
@Composable
fun WarningBanner(message: String, modifier: Modifier = Modifier, isError: Boolean = true, onClick: (() -> Unit)? = null) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (isError) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.tertiaryContainer,
        ),
        modifier = modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val color = if (isError) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onTertiaryContainer
            Icon(Icons.Outlined.ErrorOutline, contentDescription = null, tint = color)
            Text(message, style = MaterialTheme.typography.bodyMedium, color = color)
        }
    }
}

@Composable
fun Pill(text: String, color: Color) {
    Surface(color = color.copy(alpha = 0.14f), shape = MaterialTheme.shapes.small) {
        Text(text, color = color, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
    }
}

/** Situação de uma conexão da Pluggy ("Atualizada", "Com erro"…), com a cor correspondente. */
@Composable
fun HealthPill(health: ItemHealth) {
    val color = when (health) {
        ItemHealth.OK -> PrismaThemeExt.finance.income
        ItemHealth.UPDATING -> MaterialTheme.colorScheme.primary
        ItemHealth.WARNING -> MaterialTheme.colorScheme.tertiary
        ItemHealth.ERROR, ItemHealth.EXPIRED -> MaterialTheme.colorScheme.error
    }
    Pill(health.label(), color)
}
