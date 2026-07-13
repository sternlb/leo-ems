package de.baselai.leoems.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Basel-AI-Schriften (docs/app-design.md):
//   Display = Space Grotesk (700), Body = Inter, Mono/Zahlen = Space Mono.
// Die Fontdateien gehören nach app/src/main/res/font/ und werden hier zu FontFamilies gebunden.
// Bis dahin Fallback auf System-Fonts, damit das Projekt kompiliert.
val SpaceGrotesk = FontFamily.Default   // TODO: FontFamily(Font(R.font.space_grotesk_bold, FontWeight.Bold))
val Inter = FontFamily.Default          // TODO: FontFamily(Font(R.font.inter_regular))
val SpaceMono = FontFamily.Monospace    // TODO: FontFamily(Font(R.font.space_mono_regular))

val AppTypography = Typography(
    // Headlines: Space Grotesk 700
    headlineMedium = TextStyle(fontFamily = SpaceGrotesk, fontWeight = FontWeight.Bold, fontSize = 24.sp),
    titleLarge = TextStyle(fontFamily = SpaceGrotesk, fontWeight = FontWeight.Bold, fontSize = 20.sp),
    // Fließtext: Inter
    bodyLarge = TextStyle(fontFamily = Inter, fontSize = 16.sp),
    bodyMedium = TextStyle(fontFamily = Inter, fontSize = 14.sp),
    // Zahlen/technische Labels: Space Mono
    labelLarge = TextStyle(fontFamily = SpaceMono, fontWeight = FontWeight.Medium, fontSize = 14.sp),
    displaySmall = TextStyle(fontFamily = SpaceMono, fontWeight = FontWeight.Bold, fontSize = 36.sp),
)
