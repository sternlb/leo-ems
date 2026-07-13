package de.baselai.leoems.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp

// Dashboard bewusst in der Dunkel-Variante: Deep Forest + elektrische Lime-Akzente.
private val BaselAiScheme = darkColorScheme(
    primary = Lime,             // CTAs/Akzent auf dunklem Grund
    onPrimary = Waldgruen,      // Lime nie als Text — Text auf Lime ist Waldgrün
    secondary = Waldgruen,
    onSecondary = OffWhite,
    tertiary = Gelb,            // Funke, sparsam
    background = DeepForest,
    onBackground = OffWhite,
    surface = Waldgruen,        // Card-Tönung
    onSurface = OffWhite,
    outline = Grau,
)

// Scharfe Kanten: max. 2px Radius (Brand-Prinzip).
private val SharpShapes = Shapes(
    extraSmall = RoundedCornerShape(2.dp),
    small = RoundedCornerShape(2.dp),
    medium = RoundedCornerShape(2.dp),
    large = RoundedCornerShape(2.dp),
)

@Composable
fun LeoEmsTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = BaselAiScheme,
        typography = AppTypography,
        shapes = SharpShapes,
        content = content,
    )
}
