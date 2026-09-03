package com.ayloo.keyboard

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View

internal data class MicrophoneColors(
    val idle: Int,
    val recording: Int,
    val processing: Int,
    val retry: Int,
    val icon: Int = Color.WHITE,
)

/** Static, vector microphone control. It performs no animation, sound, or haptic work. */
internal class MicrophoneButtonView(
    context: Context,
    private val state: OrbState,
    private val colors: MicrophoneColors,
    private val onPress: () -> Unit,
) : View(context) {
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val icon = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    init {
        isClickable = true
        isFocusable = false
        contentDescription = when (state) {
            OrbState.RECORDING -> "Stop recording"
            OrbState.PROCESSING -> "Processing voice"
            OrbState.RETRY -> "Retry voice request"
            else -> "Start microphone"
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val radius = minOf(width, height) / 2f - dp(1f)
        fill.color = when (state) {
            OrbState.RECORDING -> colors.recording
            OrbState.PROCESSING -> colors.processing
            OrbState.RETRY, OrbState.ERROR -> colors.retry
            else -> colors.idle
        }
        if (isPressed) fill.color = darken(fill.color)
        canvas.drawCircle(width / 2f, height / 2f, radius, fill)

        val centerX = width / 2f
        val centerY = height / 2f - dp(.5f)
        icon.color = colors.icon
        icon.strokeWidth = dp(2f)
        canvas.drawRoundRect(
            RectF(centerX - dp(3.6f), centerY - dp(8f), centerX + dp(3.6f), centerY + dp(2.5f)),
            dp(3.6f),
            dp(3.6f),
            icon,
        )
        canvas.drawArc(
            RectF(centerX - dp(7f), centerY - dp(2f), centerX + dp(7f), centerY + dp(8f)),
            0f,
            180f,
            false,
            icon,
        )
        canvas.drawLine(centerX, centerY + dp(8f), centerX, centerY + dp(11f), icon)
        canvas.drawLine(centerX - dp(4f), centerY + dp(11f), centerX + dp(4f), centerY + dp(11f), icon)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return true
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                isPressed = true
                invalidate()
                onPress()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                isPressed = false
                invalidate()
                if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun darken(color: Int) = Color.rgb(
        (Color.red(color) * .78f).toInt(),
        (Color.green(color) * .78f).toInt(),
        (Color.blue(color) * .78f).toInt(),
    )

    private fun dp(value: Float) = value * resources.displayMetrics.density
}
