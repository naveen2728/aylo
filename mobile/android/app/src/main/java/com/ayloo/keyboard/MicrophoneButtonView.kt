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
    val success: Int = Color.rgb(45, 160, 88),
)

/** Static icon-only microphone control with no orb, label, animation, sound, or haptic work. */
internal class MicrophoneButtonView(
    context: Context,
    private val state: OrbState,
    private val colors: MicrophoneColors,
    private val onPress: () -> Unit,
) : View(context) {
    private val touchPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val iconPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    init {
        isClickable = true
        isFocusable = false
        isSoundEffectsEnabled = false
        isHapticFeedbackEnabled = false
        contentDescription = when (state) {
            OrbState.RECORDING -> "Stop recording"
            OrbState.PROCESSING -> "Processing voice"
            OrbState.SUCCESS -> "Voice result inserted"
            OrbState.RETRY -> "Retry voice request"
            OrbState.ERROR -> "Voice request failed"
            OrbState.IDLE -> "Start microphone"
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val iconColor = when (state) {
            OrbState.RECORDING -> colors.recording
            OrbState.PROCESSING -> colors.processing
            OrbState.RETRY, OrbState.ERROR -> colors.retry
            OrbState.SUCCESS -> colors.success
            OrbState.IDLE -> colors.idle
        }
        if (isPressed) {
            touchPaint.color = Color.argb(30, Color.red(iconColor), Color.green(iconColor), Color.blue(iconColor))
            canvas.drawCircle(width / 2f, height / 2f, minOf(width, height) * .43f, touchPaint)
        }

        val centerX = width / 2f
        val centerY = height / 2f - dp(.5f)
        iconPaint.color = iconColor
        iconPaint.strokeWidth = dp(2.25f)
        canvas.drawRoundRect(
            RectF(centerX - dp(4f), centerY - dp(8.5f), centerX + dp(4f), centerY + dp(2.5f)),
            dp(4f),
            dp(4f),
            iconPaint,
        )
        canvas.drawArc(
            RectF(centerX - dp(7.5f), centerY - dp(2f), centerX + dp(7.5f), centerY + dp(8.5f)),
            0f,
            180f,
            false,
            iconPaint,
        )
        canvas.drawLine(centerX, centerY + dp(8.5f), centerX, centerY + dp(12f), iconPaint)
        canvas.drawLine(centerX - dp(4.5f), centerY + dp(12f), centerX + dp(4.5f), centerY + dp(12f), iconPaint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return true
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                isPressed = true
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                val slop = dp(12f)
                val inside = event.x >= -slop && event.x <= width + slop &&
                    event.y >= -slop && event.y <= height + slop
                if (isPressed != inside) {
                    isPressed = inside
                    invalidate()
                }
            }
            MotionEvent.ACTION_UP -> {
                val shouldActivate = isPressed
                isPressed = false
                invalidate()
                if (shouldActivate) {
                    onPress()
                    performClick()
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                isPressed = false
                invalidate()
            }
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun dp(value: Float) = value * resources.displayMetrics.density
}
