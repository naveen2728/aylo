package com.ayloo.keyboard

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle

internal const val ACTION_MICROPHONE_PERMISSION_RESULT = "com.ayloo.keyboard.MICROPHONE_PERMISSION_RESULT"
internal const val EXTRA_MICROPHONE_GRANTED = "microphone_granted"
internal const val INTERNAL_BROADCAST_PERMISSION = "com.ayloo.keyboard.permission.INTERNAL"

/** A short-lived activity is required because an InputMethodService cannot show runtime prompts. */
class PermissionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            reportResult(true)
            finish()
        } else {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_MICROPHONE)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == REQUEST_MICROPHONE) reportResult(results.firstOrNull() == PackageManager.PERMISSION_GRANTED)
        finish()
    }

    private fun reportResult(granted: Boolean) {
        sendBroadcast(
            android.content.Intent(ACTION_MICROPHONE_PERMISSION_RESULT)
                .setPackage(packageName)
                .putExtra(EXTRA_MICROPHONE_GRANTED, granted),
            INTERNAL_BROADCAST_PERMISSION,
        )
    }

    private companion object { const val REQUEST_MICROPHONE = 100 }
}
