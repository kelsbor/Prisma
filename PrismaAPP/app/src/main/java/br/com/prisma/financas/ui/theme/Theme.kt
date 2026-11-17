package br.com.prisma.financas.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val LightColors = lightColorScheme(
    primary = LightPrimary, onPrimary = LightOnPrimary,
    primaryContainer = LightPrimaryContainer, onPrimaryContainer = LightOnPrimaryContainer,
    secondary = LightSecondary, onSecondary = LightOnSecondary,
    secondaryContainer = LightSecondaryContainer, onSecondaryContainer = LightOnSecondaryContainer,
    tertiary = LightTertiary, onTertiary = LightOnTertiary,
    tertiaryContainer = LightTertiaryContainer, onTertiaryContainer = LightOnTertiaryContainer,
    background = LightBackground, onBackground = LightOnBackground,
    surface = LightSurface, onSurface = LightOnSurface,
    surfaceVariant = LightSurfaceVariant, onSurfaceVariant = LightOnSurfaceVariant,
    surfaceContainerLowest = LightSurfaceContainerLowest, surfaceContainerLow = LightSurfaceContainerLow,
    surfaceContainer = LightSurfaceContainer, surfaceContainerHigh = LightSurfaceContainerHigh,
    surfaceContainerHighest = LightSurfaceContainerHighest,
    outline = LightOutline, outlineVariant = LightOutlineVariant,
    error = LightError, onError = LightOnError,
    errorContainer = LightErrorContainer, onErrorContainer = LightOnErrorContainer,
)

private val DarkColors = darkColorScheme(
    primary = DarkPrimary, onPrimary = DarkOnPrimary,
    primaryContainer = DarkPrimaryContainer, onPrimaryContainer = DarkOnPrimaryContainer,
    secondary = DarkSecondary, onSecondary = DarkOnSecondary,
    secondaryContainer = DarkSecondaryContainer, onSecondaryContainer = DarkOnSecondaryContainer,
    tertiary = DarkTertiary, onTertiary = DarkOnTertiary,
    tertiaryContainer = DarkTertiaryContainer, onTertiaryContainer = DarkOnTertiaryContainer,
    background = DarkBackground, onBackground = DarkOnBackground,
    surface = DarkSurface, onSurface = DarkOnSurface,
    surfaceVariant = DarkSurfaceVariant, onSurfaceVariant = DarkOnSurfaceVariant,
    surfaceContainerLowest = DarkSurfaceContainerLowest, surfaceContainerLow = DarkSurfaceContainerLow,
    surfaceContainer = DarkSurfaceContainer, surfaceContainerHigh = DarkSurfaceContainerHigh,
    surfaceContainerHighest = DarkSurfaceContainerHighest,
    outline = DarkOutline, outlineVariant = DarkOutlineVariant,
    error = DarkError, onError = DarkOnError,
    errorContainer = DarkErrorContainer, onErrorContainer = DarkOnErrorContainer,
)

/** Cores semânticas de finanças, além do esquema Material. */
@Immutable
data class FinanceColors(
    val income: Color,
    val expense: Color,
    val neutral: Color,
    val heroGradient: Brush,
)

private val LightFinance = FinanceColors(
    income = Color(0xFF0E8A5F),
    expense = Color(0xFFC62E3E),
    neutral = LightOnSurfaceVariant,
    heroGradient = Brush.linearGradient(listOf(PrismaDeep, PrismaViolet)),
)

private val DarkFinance = FinanceColors(
    income = Color(0xFF5FD4A0),
    expense = Color(0xFFFF8A94),
    neutral = DarkOnSurfaceVariant,
    heroGradient = Brush.linearGradient(listOf(Color(0xFF2A1F6E), Color(0xFF4A3CC4))),
)

val LocalFinanceColors = staticCompositionLocalOf { LightFinance }

private val PrismaShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(32.dp),
)

/**
 * Tema do Prisma. Cor dinâmica do Android 12+ desligada de propósito
 * para manter a identidade visual da marca.
 */
@Composable
fun PrismaTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    CompositionLocalProvider(LocalFinanceColors provides if (darkTheme) DarkFinance else LightFinance) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkColors else LightColors,
            typography = PrismaTypography,
            shapes = PrismaShapes,
            content = content,
        )
    }
}

object PrismaThemeExt {
    val finance: FinanceColors
        @Composable get() = LocalFinanceColors.current
}
