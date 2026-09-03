package com.ayloo.keyboard

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.view.ViewCompat
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import androidx.customview.widget.ExploreByTouchHelper
import java.util.ArrayDeque
import kotlin.math.abs

internal enum class FastKeyStyle { LETTER, FUNCTION, ACCENT, SELECTED }

internal data class FastKey(
    val label: String,
    val weight: Float = 1f,
    val style: FastKeyStyle = FastKeyStyle.LETTER,
    val description: String = label,
    val alternateLabel: String? = null,
    val repeatable: Boolean = false,
    val pressOnDown: Boolean = false,
    val spacer: Boolean = false,
    val onPress: () -> Unit = {},
    val onLongPress: (() -> Unit)? = null,
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
 * One lightweight drawing and touch surface for the complete key grid.
 *
 * Every finger owns an independent candidate. Character candidates may be corrected while the
 * finger is down and are committed on release, while modifiers and backspace remain immediate.
 * This preserves fast overlapping taps without making an inaccurate initial landing irreversible.
 */
internal class FastKeyboardView(
    context: Context,
    private val colors: FastKeyboardColors,
    rows: List<List<FastKey>>,
) : View(context) {
    private data class Geometry(val key: FastKey, val bounds: RectF, val row: Int)
    private data class ActivePress(
        var geometryIndex: Int,
        val committedOnDown: Boolean,
        val ordinarySequence: Long? = null,
        var longPressTriggered: Boolean = false,
    )
    private data class CompletedPress(val key: FastKey?, val shouldCommit: Boolean)

    private val handler = Handler(Looper.getMainLooper())
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1f)
    }
    private val regularTypeface = Typeface.create("sans-serif", Typeface.NORMAL)
    private val boldTypeface = Typeface.create("sans-serif", Typeface.BOLD)
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = regularTypeface
    }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.RIGHT
        typeface = regularTypeface
    }
    private val clipBounds = Rect()
    private val clipRect = RectF()
    private var keyRows = rows
    private var pendingRows: List<List<FastKey>>? = null
    private val geometries = mutableListOf<Geometry>()
    private val rowGeometryIndices = mutableListOf<IntArray>()
    private val activePointers = mutableMapOf<Int, ActivePress>()
    private val longPressRunnables = mutableMapOf<Int, Runnable>()
    private val pressedCounts = mutableMapOf<Int, Int>()
    private val ordinaryPressOrder = ArrayDeque<Long>()
    private val completedPresses = mutableMapOf<Long, CompletedPress>()
    private var nextOrdinarySequence = 0L
    private var afterPointersReleased: (() -> Unit)? = null
    private var cancellingAllPointers = false
    private var repeatPointerId: Int? = null
    private var repeatKey: FastKey? = null
    private var repeatCount = 0
    private val repeatRunnable = object : Runnable {
        override fun run() {
            val key = repeatKey ?: return
            key.onPress()
            repeatCount += 1
            handler.postDelayed(this, when {
                repeatCount > 28 -> 28L
                repeatCount > 10 -> 30L
                else -> 40L
            })
        }
    }
    private val accessibilityHelper = object : ExploreByTouchHelper(this) {
        override fun getVirtualViewAt(x: Float, y: Float): Int {
            if (x !in 0f..width.toFloat() || y !in 0f..height.toFloat()) return ExploreByTouchHelper.INVALID_ID
            val index = findKey(x, y) ?: return ExploreByTouchHelper.INVALID_ID
            return if (geometries.getOrNull(index)?.key?.spacer == false) index else ExploreByTouchHelper.INVALID_ID
        }

        override fun getVisibleVirtualViews(virtualViewIds: MutableList<Int>) {
            geometries.forEachIndexed { index, geometry ->
                if (!geometry.key.spacer) virtualViewIds.add(index)
            }
        }

        override fun onPopulateNodeForVirtualView(virtualViewId: Int, node: AccessibilityNodeInfoCompat) {
            val geometry = geometries.getOrNull(virtualViewId) ?: return
            node.text = geometry.key.label
            node.contentDescription = geometry.key.description
            node.className = android.widget.Button::class.java.name
            node.isClickable = true
            node.setBoundsInParent(
                Rect(
                    geometry.bounds.left.toInt(),
                    geometry.bounds.top.toInt(),
                    geometry.bounds.right.toInt(),
                    geometry.bounds.bottom.toInt(),
                ),
            )
            node.addAction(AccessibilityNodeInfo.ACTION_CLICK)
            if (geometry.key.onLongPress != null) {
                node.isLongClickable = true
                node.addAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)
            }
        }

        override fun onPerformActionForVirtualView(virtualViewId: Int, action: Int, arguments: Bundle?): Boolean {
            val key = geometries.getOrNull(virtualViewId)?.key ?: return false
            return when (action) {
                AccessibilityNodeInfo.ACTION_CLICK -> {
                    key.onPress()
                    key.onRelease?.invoke()
                    sendEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_CLICKED)
                    true
                }
                AccessibilityNodeInfo.ACTION_LONG_CLICK -> {
                    key.onLongPress?.invoke() ?: return false
                    sendEventForVirtualView(virtualViewId, AccessibilityEvent.TYPE_VIEW_LONG_CLICKED)
                    true
                }
                else -> false
            }
        }
    }

    init {
        isClickable = true
        isFocusable = false
        isSoundEffectsEnabled = false
        isHapticFeedbackEnabled = false
        contentDescription = "Ayloo keyboard"
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        ViewCompat.setAccessibilityDelegate(this, accessibilityHelper)
    }

    /** Row changes are delayed until all active fingers lift, preventing dropped overlap taps. */
    fun updateRows(rows: List<List<FastKey>>) {
        if (activePointers.isNotEmpty()) {
            pendingRows = rows
            return
        }
        applyRows(rows)
    }

    private fun applyRows(rows: List<List<FastKey>>) {
        stopRepeat()
        keyRows = rows
        pendingRows = null
        pressedCounts.clear()
        rebuildGeometry(width, height)
        accessibilityHelper.invalidateRoot()
        invalidate()
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        super.onSizeChanged(width, height, oldWidth, oldHeight)
        rebuildGeometry(width, height)
        accessibilityHelper.invalidateRoot()
    }

    private fun rebuildGeometry(width: Int, height: Int) {
        geometries.clear()
        rowGeometryIndices.clear()
        if (width <= 0 || height <= 0 || keyRows.isEmpty()) return
        val side = dp(2f)
        val horizontalGap = dp(4f)
        val verticalInset = dp(2f)
        val rowHeight = height.toFloat() / keyRows.size
        keyRows.forEachIndexed { rowIndex, row ->
            val firstGeometry = geometries.size
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
                // Spacers keep their geometry as intentional dead zones. Without this, nearest-key
                // targeting turns visibly blank number-pad cells into surprising live keys.
                geometries += Geometry(key, bounds, rowIndex)
                left += keyWidth + horizontalGap
            }
            rowGeometryIndices += IntArray(geometries.size - firstGeometry) { firstGeometry + it }
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val hasClip = canvas.getClipBounds(clipBounds)
        clipRect.set(clipBounds)
        geometries.forEachIndexed { index, geometry ->
            if (hasClip && !RectF.intersects(geometry.bounds, clipRect)) return@forEachIndexed
            val key = geometry.key
            if (key.spacer) return@forEachIndexed
            val baseColor = when (key.style) {
                FastKeyStyle.LETTER -> colors.key
                FastKeyStyle.FUNCTION -> colors.functionKey
                FastKeyStyle.ACCENT -> colors.accent
                FastKeyStyle.SELECTED -> colors.selected
            }
            fillPaint.color = if ((pressedCounts[index] ?: 0) > 0) darken(baseColor) else baseColor
            canvas.drawRoundRect(geometry.bounds, dp(7f), dp(7f), fillPaint)
            if (Color.alpha(colors.stroke) != 0) {
                strokePaint.color = colors.stroke
                canvas.drawRoundRect(geometry.bounds, dp(7f), dp(7f), strokePaint)
            }

            textPaint.color = if (key.style == FastKeyStyle.ACCENT) colors.accentText else colors.text
            textPaint.textSize = sp(
                when {
                    key.label.length >= 6 -> 11.5f
                    key.label.length >= 3 -> 13f
                    else -> 20f
                },
            )
            textPaint.typeface = if (key.style == FastKeyStyle.SELECTED) boldTypeface else regularTypeface
            val metrics = textPaint.fontMetrics
            val baseline = geometry.bounds.centerY() - (metrics.ascent + metrics.descent) / 2f
            canvas.drawText(key.label, geometry.bounds.centerX(), baseline, textPaint)
            key.alternateLabel?.let { alternate ->
                hintPaint.color = if (key.style == FastKeyStyle.ACCENT) colors.accentText else colors.text
                hintPaint.alpha = 150
                hintPaint.textSize = sp(8.5f)
                canvas.drawText(alternate, geometry.bounds.right - dp(5f), geometry.bounds.top + dp(11f), hintPaint)
                hintPaint.alpha = 255
            }
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> pressPointer(event, event.actionIndex)
            MotionEvent.ACTION_MOVE -> updatePointers(event)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> releasePointer(event.getPointerId(event.actionIndex), commit = true)
            MotionEvent.ACTION_CANCEL -> cancelAllPointers()
        }
        return true
    }

    override fun dispatchHoverEvent(event: MotionEvent): Boolean {
        return accessibilityHelper.dispatchHoverEvent(event) || super.dispatchHoverEvent(event)
    }

    private fun pressPointer(event: MotionEvent, pointerIndex: Int) {
        parent?.requestDisallowInterceptTouchEvent(true)
        val pointerId = event.getPointerId(pointerIndex)
        if (pointerId in activePointers) return
        val geometryIndex = findKey(event.getX(pointerIndex), event.getY(pointerIndex)) ?: return
        val key = geometries.getOrNull(geometryIndex)?.key ?: return
        if (key.spacer) return
        val committedOnDown = key.pressOnDown || key.repeatable
        val ordinarySequence = if (committedOnDown) {
            null
        } else {
            val sequence = nextOrdinarySequence
            nextOrdinarySequence += 1
            ordinaryPressOrder.addLast(sequence)
            sequence
        }
        activePointers[pointerId] = ActivePress(geometryIndex, committedOnDown, ordinarySequence)
        markPressed(geometryIndex, 1)
        if (key.pressOnDown || key.repeatable) key.onPress()
        if (key.repeatable) startRepeat(pointerId, key)
        else if (!key.pressOnDown && key.onLongPress != null) scheduleLongPress(pointerId, geometryIndex, key)
    }

    private fun updatePointers(event: MotionEvent) {
        for (pointerIndex in 0 until event.pointerCount) {
            val pointerId = event.getPointerId(pointerIndex)
            val active = activePointers[pointerId] ?: continue
            val x = event.getX(pointerIndex)
            val y = event.getY(pointerIndex)
            if (active.committedOnDown) {
                val bounds = geometries.getOrNull(active.geometryIndex)?.bounds ?: continue
                val slop = dp(18f)
                if (x < bounds.left - slop || x > bounds.right + slop || y < bounds.top - slop || y > bounds.bottom + slop) {
                    releasePointer(pointerId, commit = false)
                }
                continue
            }
            if (x < -dp(18f) || x > width + dp(18f) || y < -dp(18f) || y > height + dp(18f)) {
                releasePointer(pointerId, commit = false)
                continue
            }
            val nextIndex = findKey(x, y, active.geometryIndex) ?: continue
            if (nextIndex != active.geometryIndex) {
                cancelLongPress(pointerId)
                markPressed(active.geometryIndex, -1)
                active.geometryIndex = nextIndex
                markPressed(nextIndex, 1)
            }
        }
    }

    private fun releasePointer(pointerId: Int, commit: Boolean) {
        val active = activePointers.remove(pointerId) ?: return
        cancelLongPress(pointerId)
        val geometry = geometries.getOrNull(active.geometryIndex)
        markPressed(active.geometryIndex, -1)
        if (repeatPointerId == pointerId) stopRepeat()
        active.ordinarySequence?.let { sequence ->
            completedPresses[sequence] = CompletedPress(
                key = geometry?.key,
                shouldCommit = commit && !active.longPressTriggered && geometry?.key?.spacer != true,
            )
            flushCompletedPresses()
        }
        geometry?.key?.onRelease?.invoke()
        if (commit) performClick()
        if (activePointers.isEmpty()) {
            pendingRows?.let(::applyRows)
            val deferred = afterPointersReleased
            afterPointersReleased = null
            if (commit) deferred?.invoke()
        }
    }

    private fun cancelAllPointers() {
        cancellingAllPointers = true
        val pointerIds = activePointers.keys.toList()
        pointerIds.forEach { releasePointer(it, commit = false) }
        cancellingAllPointers = false
        activePointers.clear()
        pressedCounts.clear()
        stopRepeat()
        longPressRunnables.values.forEach(handler::removeCallbacks)
        longPressRunnables.clear()
        ordinaryPressOrder.clear()
        completedPresses.clear()
        afterPointersReleased = null
        pendingRows?.let(::applyRows)
        invalidate()
    }

    /** Zero-allocation nearest-center targeting with a small upward contact correction. */
    private fun findKey(x: Float, y: Float, currentIndex: Int? = null): Int? {
        if (geometries.isEmpty() || keyRows.isEmpty() || height <= 0) return null
        val correctedY = y - dp(3.5f)
        val rowHeight = height.toFloat() / keyRows.size
        val targetRow = (correctedY / rowHeight).toInt().coerceIn(0, keyRows.lastIndex)
        var bestIndex = -1
        var bestScore = Float.MAX_VALUE
        val firstRow = (targetRow - 1).coerceAtLeast(0)
        val lastRow = (targetRow + 1).coerceAtMost(rowGeometryIndices.lastIndex)
        for (row in firstRow..lastRow) {
            val verticalPenalty = abs(row - targetRow) * .35f
            for (index in rowGeometryIndices[row]) {
                val bounds = geometries[index].bounds
                val halfWidth = (bounds.width() / 2f).coerceAtLeast(1f)
                val halfHeight = (bounds.height() / 2f).coerceAtLeast(1f)
                val dx = (x - bounds.centerX()) / halfWidth
                val dy = (correctedY - bounds.centerY()) / halfHeight
                val score = dx * dx + dy * dy * 1.18f + verticalPenalty
                if (score < bestScore) {
                    bestScore = score
                    bestIndex = index
                }
            }
        }
        if (bestIndex < 0) return null
        if (currentIndex != null && currentIndex in geometries.indices && currentIndex != bestIndex) {
            val current = geometries[currentIndex].bounds
            val dx = (x - current.centerX()) / (current.width() / 2f).coerceAtLeast(1f)
            val dy = (correctedY - current.centerY()) / (current.height() / 2f).coerceAtLeast(1f)
            val currentScore = dx * dx + dy * dy * 1.18f
            if (currentScore <= bestScore + TARGET_SWITCH_HYSTERESIS) return currentIndex
        }
        return bestIndex
    }

    private fun markPressed(index: Int, delta: Int) {
        val next = (pressedCounts[index] ?: 0) + delta
        if (next <= 0) pressedCounts.remove(index) else pressedCounts[index] = next
        geometries.getOrNull(index)?.bounds?.let { bounds ->
            invalidate(
                bounds.left.toInt() - 2,
                bounds.top.toInt() - 2,
                bounds.right.toInt() + 2,
                bounds.bottom.toInt() + 2,
            )
        }
    }

    /** Runs layout-changing actions only after every overlapping character has been committed. */
    fun runAfterPointersReleased(action: () -> Unit) {
        if (activePointers.isEmpty()) action() else afterPointersReleased = action
    }

    private fun flushCompletedPresses() {
        if (cancellingAllPointers) return
        while (ordinaryPressOrder.isNotEmpty()) {
            val sequence = ordinaryPressOrder.first()
            val completed = completedPresses.remove(sequence) ?: break
            ordinaryPressOrder.removeFirst()
            if (completed.shouldCommit) completed.key?.onPress?.invoke()
        }
    }

    private fun startRepeat(pointerId: Int, key: FastKey) {
        stopRepeat()
        repeatPointerId = pointerId
        repeatKey = key
        repeatCount = 0
        handler.postDelayed(repeatRunnable, 270L)
    }

    private fun scheduleLongPress(pointerId: Int, geometryIndex: Int, key: FastKey) {
        val action = key.onLongPress ?: return
        val runnable = Runnable {
            val active = activePointers[pointerId] ?: return@Runnable
            if (active.geometryIndex != geometryIndex || active.committedOnDown) return@Runnable
            longPressRunnables.remove(pointerId)
            active.longPressTriggered = true
            action()
        }
        longPressRunnables[pointerId] = runnable
        handler.postDelayed(runnable, LONG_PRESS_DELAY_MS)
    }

    private fun cancelLongPress(pointerId: Int) {
        longPressRunnables.remove(pointerId)?.let(handler::removeCallbacks)
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

    private companion object {
        const val TARGET_SWITCH_HYSTERESIS = .18f
        const val LONG_PRESS_DELAY_MS = 390L
    }
}
