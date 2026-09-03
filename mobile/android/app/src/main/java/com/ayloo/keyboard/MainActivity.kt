package com.ayloo.keyboard

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.inputmethod.InputMethodManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Small, polished setup surface; typing itself happens through [AylooInputMethodService]. */
class MainActivity : ComponentActivity() {
    private val keyboardEnabled = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshKeyboardState()
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = AylooPurple,
                    surface = Panel,
                    background = Background,
                    onSurface = Color.White,
                ),
            ) {
                AylooSetupScreen(
                    enabled = keyboardEnabled.value,
                    onEnable = { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) },
                    onChoose = {
                        (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
                    },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshKeyboardState()
    }

    private fun refreshKeyboardState() {
        val manager = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        keyboardEnabled.value = manager.enabledInputMethodList.any { it.packageName == packageName }
    }
}

@Composable
private fun AylooSetupScreen(enabled: Boolean, onEnable: () -> Unit, onChoose: () -> Unit) {
    var testText by remember { mutableStateOf("") }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFF12131A), Color(0xFF191629), Color(0xFF12131A)),
                ),
            )
            .padding(horizontal = 22.dp, vertical = 24.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().align(Alignment.Center),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Surface(
                modifier = Modifier.clip(RoundedCornerShape(24.dp)),
                color = Color(0xFF6757E8),
                shadowElevation = 12.dp,
            ) {
                Text("✦", color = Color.White, fontSize = 30.sp, modifier = Modifier.padding(horizontal = 17.dp, vertical = 10.dp))
            }
            Spacer(Modifier.height(18.dp))
            Text("Ayloo Keyboard", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.SemiBold)
            Text(
                "Type normally. Dictate exactly. Ask AI anywhere.",
                color = Muted,
                fontSize = 15.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 7.dp, bottom = 24.dp),
            )

            Card(
                colors = CardDefaults.cardColors(containerColor = Panel),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    SetupStep(
                        number = "1",
                        title = if (enabled) "Keyboard enabled" else "Enable Ayloo",
                        detail = if (enabled) "Android can now show Ayloo in the keyboard picker." else "Android requires you to approve every installed keyboard.",
                        complete = enabled,
                    )
                    SetupStep(
                        number = "2",
                        title = "Choose Ayloo",
                        detail = "Open the keyboard picker and select Ayloo Keyboard.",
                        complete = false,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                        Button(
                            onClick = onEnable,
                            modifier = Modifier.weight(1f).height(48.dp),
                            shape = RoundedCornerShape(14.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = if (enabled) Color(0xFF32313D) else AylooPurple),
                        ) { Text(if (enabled) "Settings" else "Enable") }
                        Button(
                            onClick = onChoose,
                            enabled = enabled,
                            modifier = Modifier.weight(1f).height(48.dp),
                            shape = RoundedCornerShape(14.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = AylooPurple),
                        ) { Text("Choose keyboard") }
                    }
                }
            }

            Spacer(Modifier.height(14.dp))
            OutlinedTextField(
                value = testText,
                onValueChange = { testText = it },
                enabled = enabled,
                label = { Text(if (enabled) "Tap here to test Ayloo" else "Enable Ayloo to test") },
                placeholder = { Text("Try the keys, Dictate, or AI…") },
                minLines = 2,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
            )
            Text(
                "Dictate inserts your transcript. AI inserts the answer and copies it. Voice is disabled in password fields.",
                color = Muted,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 14.dp),
            )
            Text("Internal beta · ${BuildConfig.VERSION_NAME}", color = Color(0xFF777789), fontSize = 11.sp)
        }
    }
}

@Composable
private fun SetupStep(number: String, title: String, detail: String, complete: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            color = if (complete) Color(0xFF315C4B) else Color(0xFF34323F),
            shape = RoundedCornerShape(12.dp),
        ) {
            Text(
                if (complete) "✓" else number,
                color = if (complete) Color(0xFF77D7AA) else Color.White,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
        Column(Modifier.padding(start = 12.dp)) {
            Text(title, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            Text(detail, color = Muted, fontSize = 12.sp, lineHeight = 16.sp)
        }
    }
}

private val AylooPurple = Color(0xFF7868FF)
private val Background = Color(0xFF12131A)
private val Panel = Color(0xFF202029)
private val Muted = Color(0xFFB4B3C2)
