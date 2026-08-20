package com.ayloo.keyboard

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val KeyboardBackground = Color(0xFF16151D)
private val KeyBackground = Color(0xFF302E3A)
private val OrbColor = Color(0xFF7868FF)

@Composable
fun KeyboardScreen(
    orbState: OrbState,
    status: String,
    symbols: Boolean,
    uppercase: Boolean,
    onOrb: () -> Unit,
    onRetry: () -> Unit,
    onDiscard: () -> Unit,
    onKey: (String) -> Unit,
    onBackspace: () -> Unit,
    onSymbols: () -> Unit,
    onCaps: () -> Unit,
    onSpace: () -> Unit,
    onEnter: () -> Unit,
    onSwitchKeyboard: () -> Unit,
) {
    val letters = if (uppercase) listOf("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM") else listOf("qwertyuiop", "asdfghjkl", "zxcvbnm")
    val rows = if (symbols) listOf("1234567890", "-/:;()₹&@\"", "#+=!?.,") else letters
    MaterialTheme {
        Column(
            modifier = Modifier.fillMaxWidth().background(KeyboardBackground).padding(4.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(status, color = Color.White, fontSize = 12.sp, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
            if (orbState == OrbState.RETRY) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                    KeyboardButton("Retry", Modifier.weight(1f), onRetry)
                    KeyboardButton("Discard", Modifier.weight(1f), onDiscard)
                }
            }
            rows.forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(3.dp), modifier = Modifier.fillMaxWidth()) {
                    row.forEach { char -> KeyboardButton(char.toString(), Modifier.weight(1f)) { onKey(char.toString()) } }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.fillMaxWidth()) {
                KeyboardButton(if (symbols) "ABC" else "123", Modifier.weight(1.1f), onSymbols)
                KeyboardButton("⇧", Modifier.weight(0.9f), onCaps)
                KeyboardButton("⌫", Modifier.weight(1.1f), onBackspace)
                OrbButton(orbState, Modifier.weight(1.4f), onOrb)
                KeyboardButton("space", Modifier.weight(3f), onSpace)
                KeyboardButton("↵", Modifier.weight(1.1f), onEnter)
                KeyboardButton("⌨", Modifier.weight(1.1f), onSwitchKeyboard)
            }
        }
    }
}

@Composable
private fun KeyboardButton(label: String, modifier: Modifier, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(8.dp),
        colors = ButtonDefaults.buttonColors(containerColor = KeyBackground, contentColor = Color.White),
        contentPadding = ButtonDefaults.ContentPadding,
    ) { Text(label, fontSize = 16.sp) }
}

@Composable
private fun OrbButton(state: OrbState, modifier: Modifier, onClick: () -> Unit) {
    val label = when (state) {
        OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> "● AI"
        OrbState.RECORDING -> "■ Stop"
        OrbState.PROCESSING -> "…"
        OrbState.RETRY -> "↻ Retry"
    }
    Button(
        onClick = onClick,
        enabled = state != OrbState.PROCESSING,
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(24.dp),
        colors = ButtonDefaults.buttonColors(containerColor = OrbColor, contentColor = Color.White),
    ) { Text(label, fontSize = 14.sp) }
}
