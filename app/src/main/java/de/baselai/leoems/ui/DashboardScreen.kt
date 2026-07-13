package de.baselai.leoems.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import de.baselai.leoems.data.StatusDto
import de.baselai.leoems.ui.theme.Gelb
import de.baselai.leoems.ui.theme.Lime

// Dashboard (Spec §9.2): Erzeugung, Hausverbraucher (Wallbox), Batterie,
// Prognose, Klartext-Begründung. Branding: Deep-Forest-Grund, Lime-Akzente,
// Space-Mono-Zahlen, Gelb-Funke für aktive Garantieladung.

@Composable
fun DashboardScreen(status: StatusDto?) {
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Leo-EMS", style = MaterialTheme.typography.headlineMedium)

        if (status == null) {
            Text("Verbinde mit dem Backend …", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        // Statuszeile: Klartext-Begründung (REQ-050)
        StatusCard(status)

        // Kennzahlen-Kacheln (Space-Mono-Zahlen)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            MetricTile("Überschuss", "${status.ueberschuss_w ?: 0} W", Modifier.weight(1f))
            MetricTile("Wallbox", if (status.laedt == true) "${status.strom_a}A ${status.phasen}p" else "aus", Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            MetricTile("Batterie", "${status.soc_batterie?.toInt() ?: 0} %", Modifier.weight(1f))
            MetricTile("Auto", "${status.soc_fahrzeug?.toInt() ?: 0} %", Modifier.weight(1f))
        }

        if (status.garantieladung == true) {
            Text("⚡ Garantieladung aktiv", color = Gelb, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun StatusCard(status: StatusDto) {
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Text(status.modus ?: "—", color = Lime, style = MaterialTheme.typography.labelLarge)
            Text(status.grund ?: "", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun MetricTile(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(16.dp)) {
            Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
            Text(value, style = MaterialTheme.typography.displaySmall)
        }
    }
}
