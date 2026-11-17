package br.com.prisma.financas.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val Base = Typography()

val PrismaTypography = Typography(
    displaySmall = Base.displaySmall.copy(fontWeight = FontWeight.SemiBold),
    headlineLarge = Base.headlineLarge.copy(fontWeight = FontWeight.SemiBold),
    headlineMedium = Base.headlineMedium.copy(fontWeight = FontWeight.SemiBold),
    headlineSmall = Base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
    titleLarge = Base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
    titleMedium = Base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    titleSmall = Base.titleSmall.copy(fontWeight = FontWeight.SemiBold),
    labelLarge = Base.labelLarge.copy(fontWeight = FontWeight.SemiBold),
)

/** Algarismos tabulares para valores alinharem em listas. */
val MoneyTextStyle = TextStyle(fontFeatureSettings = "tnum")

val MoneyHeroStyle = TextStyle(
    fontSize = 34.sp,
    lineHeight = 40.sp,
    fontWeight = FontWeight.SemiBold,
    fontFeatureSettings = "tnum",
    letterSpacing = (-0.5).sp,
)
