package com.ayloo.keyboard

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs

internal enum class FastKeyStyle { LETTER, FUNCTION, ACCENT, SELECTED }

internal data class FastKey(
    val label: String,
    val weight: Float = 1f,
    val style: FastKeyStyle = FastKeyStyle.LETTER,
    val description: String = label,
    val repeatable: Boolean = false,
    val spacer: Boolean = false,
    val onPress: () -> Unit = {},
    val onRelease: (() -> Unit)? = null,
)

internal data class FastKeyboardColors(
    val key: Int,
    val functionKey: Int,
    val accent: Int,
    val selected: Int,
    val text: Int,
    val accentText: Int = Color.WHITE,
    val stroke: Int,
)

/**
 * A single drawing and touch surface for the complete key grid.
 *
 * Unlike a hierarchy of Buttons/TextViews, this receives every pointer in one event stream. That
 * means a second finger may press the next letter before the first finger lifts without Android
 * routing either event to the wrong child. Visible gaps are mapped to the nearest key in their row.
 */
internal class FastKeyboardView(
    context: Context,
    private val colors: FastKeyboardColors,
    rows: List<List<FastKey>>,
) : View(context) {
    private data class Geometry(val key: FastKey, val bounds: RectF, val row: Int)

    private val handler = Handler(Looper.getMainLooper())
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create("sans-serif", Typeface.NORMAL)
    }
    private var keyRows = rows
    private val geometries = mutableListOf<Geometry>()
    private val activePointers = mutableMapOf<Int, Int>()
    private val pressedIndices = mutableSetOf<Int>()
    private var repeatPointerId: Int? = null
    private var repeatKey: FastKey? = null
    private var repeatCount = 0
    private val repeatRunnable = object : Runnable {
        override fun run() {
            val key = repeatKey ?: return
            key.onPress()
            repeatCount += 1
            handler.postDelayed(this, if (repeatCount > 10) 28L else 40L)
        }
    }

    init {
        isClickable = true
        isFocusable = false
        contentDescription = "Ayloo keyboard"
    }

    fun updateRows(rows: List<List<FastKey>>) {
        stopRepeat()
        keyRows = rows
        activePointers.clear()
        pressedIndices.clear()
        rebuildGeometry(width, height)
        invalidate()
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        super.onSizeChanged(width, height, oldWidth, oldHeight)
        rebuildGeometry(width, height)
    }

    private fun rebuildGeometry(width: Int, height: Int) {
        geometries.clear()
        if (width <= 0 || height <= 0 || keyRows.isEmpty()) return
        val side = dp(2f)
        val horizontalGap = dp(4f)
        val verticalInset = dp(2f)
        val rowHeight = height.toFloat() / keyRows.size
        keyRows.forEachIndexed { rowIndex, row ->
            val totalWeight = row.sumOf { it.weight.toDouble() }.toFloat().coerceAtLeast(1f)
            val available = width - side * 2f - horizontalGap * (row.size - 1).coerceAtLeast(0)
            val unit = available / totalWeight
            var left = side
            row.forEach { key ->
                val keyWidth = unit * key.weight
                val bounds = RectF(
                    left,
                    rowIndex * rowHeight + verticalInset,
                    left + keyWidth,
                    (rowIndex + 1) * rowHeight - verticalInset,
                )
                if (!key.spacer) geometries += Geometry(key, bounds, rowIndex)
                left += keyWidth + horizontalGap
            }
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        geometries.forEachIndexed { index, geometry ->
            val key = geometry.key
            val baseColor = when (key.style) {
                FastKeyStyle.LETTER -> colors.key
                FastKeyStyle.FUNCTION -> colors.functionKey
                FastKeyStyle.ACCENT -> colors.accent
                FastKeyStyle.SELECTED -> colors.selected
            }
            fillPaint.color = if (index in pressedIndices) darken(baseColor) else baseColor
            canvas.drawRoundRect(geometry.bounds, dp(7f), dp(7f), fillPaint)
            strokePaint.color = colors.stroke
            canvas.drawRoundRect(geometry.bounds, dp(7f), dp(7f), strokePaint)

            textPaint.color = if (key.style == FastKeyStyle.ACCENT) colors.accentText else colors.text
            textPaint.textSize = sp(
                when {
                    key.label.length >= 6 -> 11.5f
                    key.label.length >= 3 -> 13f
                    else -> 20f
                },
            )
            textPaint.typeface = Typeface.create(
                "sans-serif",
                if (key.style == FastKeyStyle.SELECTED) Typeface.BOLD else Typeface.NORMAL,
            )
            val metrics = textPaint.fontMetrics
            val baseline = geometry.bounds.centerY() - (metrics.ascent + metrics.descent) / 2f
            canvas.drawText(key.label, geometry.bounds.centerX(), baseline, textPaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> pressPointer(event, event.actionIndex)
            MotionEvent.ACTION_MOVE -> updatePointers(event)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> releasePointer(event.getPointerId(event.actionIndex))
            MotionEvent.ACTION_CANCEL -> cancelAllPointers()
        }
        return true
    }

    private fun pressPointer(event: MotionEvent, pointerIndex: Int) {
        parent?.requestDisallowInterceptTouchEvent(true)
        val pointerId = event.getPointerId(pointerIndex)
        val geometryIndex = findKey(event.getX(pointerIndex), event.getY(pointerIndex)) ?: return
        activePointers[pointerId] = geometryIndex
        pressedIndices += geometryIndex
        invalidate()
        val key = geometries.getOrNull(geometryIndex)?.key ?: return
        // Input dispatch is the first work performed for the pointer.
        key.onPress()
        if (key.repeatable) startRepeat(pointerId, key)
    }

    private fun updatePointers(event: MotionEvent) {
        for (pointerIndex in 0 until event.pointerCount) {
            val pointerId = event.getPointerId(pointerIndex)
            val originalIndex = activePointers[pointerId] ?: continue
            val currentIndex = findKey(event.getX(pointerIndex), event.getY(pointerIndex))
            if (currentIndex != originalIndex) releasePointer(pointerId)
        }
    }

    private fun releasePointer(pointerId: Int) {
        val geometryIndex = activePointers.remove(pointerId) ?: return
        pressedIndices.remove(geometryIndex)
        if (repeatPointerId == pointerId) stopRepeat()
        geometries.getOrNull(geometryIndex)?.key?.onRelease?.invoke()
        invalidate()
    }

    private fun cancelAllPointers() {
        val releaseCallbacks = activePointers.values.mapNotNull { geometries.getOrNull(it)?.key?.onRelease }
        activePointers.clear()
        pressedIndices.clear()
        stopRepeat()
        releaseCallbacks.forEach { it() }
        invalidate()
    }

    private fun findKey(x: Float, y: Float): Int? {
        if (geometries.isEmpty() || keyRows.isEmpty()) return null
        val row = ((y.coerceIn(0f, height.toFloat().coerceAtLeast(1f) - 1f) / height) * keyRows.size)
            .toInt().coerceIn(0, keyRows.lastIndex)
        val candidates = geometries.withIndex().filter { it.value.row == row }
        candidates.firstOrNull { x >= it.value.bounds.left && x <= it.value.bounds.right }?.let { return it.index }
        return candidates.minByOrNull { indexed ->
            when {
                x < indexed.value.bounds.left -> indexed.value.bounds.left - x
                x > indexed.value.bounds.right -> x - indexed.value.bounds.right
                else -> abs(x - indexed.value.bounds.centerX())
            }
        }?.index
    }

    private fun startRepeat(pointerId: Int, key: FastKey) {
        stopRepeat()
        repeatPointerId = pointerId
        repeatKey = key
        repeatCount = 0
        handler.postDelayed(repeatRunnable, 280L)
    }

    private fun stopRepeat() {
        handler.removeCallbacks(repeatRunnable)
        repeatPointerId = null
        repeatKey = null
        repeatCount = 0
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    override fun onDetachedFromWindow() {
        cancelAllPointers()
        super.onDetachedFromWindow()
    }

    private fun darken(color: Int) = Color.rgb(
        (Color.red(color) * .76f).toInt(),
        (Color.green(color) * .76f).toInt(),
        (Color.blue(color) * .76f).toInt(),
    )

    private fun dp(value: Float) = value * resources.displayMetrics.density
    private fun sp(value: Float) = value * resources.displayMetrics.scaledDensity
}
