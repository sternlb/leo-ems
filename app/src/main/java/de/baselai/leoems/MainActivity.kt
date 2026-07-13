package de.baselai.leoems

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import de.baselai.leoems.data.StatusDto
import de.baselai.leoems.ui.DashboardScreen
import de.baselai.leoems.ui.theme.LeoEmsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            LeoEmsTheme {
                // TODO: Status per Retrofit/WebSocket vom Backend laden (EmsApi.status).
                //       Backend-Adresse + Token aus den App-Einstellungen (mDNS-Discovery).
                var status by remember { mutableStateOf<StatusDto?>(null) }
                DashboardScreen(status)
            }
        }
    }
}
