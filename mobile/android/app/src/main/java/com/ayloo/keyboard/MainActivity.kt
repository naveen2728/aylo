package com.ayloo.keyboard

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Entry point for enabling the keyboard; typing itself happens through the InputMethodService. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Column(
                    modifier = Modifier.fillMaxSize().background(Color(0xFF16151D)).padding(28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text("Ayloo Keyboard", color = Color.White, fontSize = 28.sp)
                    Text(
                        "1. Enable Ayloo Keyboard in Android settings.\n\n" +
                            "2. Open any app with a text box.\n\n" +
                            "3. Select Ayloo from the keyboard picker and tap the AI orb to speak.",
                        modifier = Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 28.dp),
                        color = Color(0xFFD4D0E0),
                        textAlign = TextAlign.Start,
                        fontSize = 16.sp,
                    )
                    Button(onClick = { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }) {
                        Text("Enable Ayloo Keyboard")
                    }
                }
            }
        }
    }
}
