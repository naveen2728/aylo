package com.ayloo.keyboard

import android.Manifest
import android.animation.Animator
import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.InputType
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.SoundEffectConstants
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import java.util.ArrayDeque
import java.util.Locale
import java.util.concurrent.Executors

enum class OrbState { IDLE, RECORDING, PROCESSING, SUCCESS, RETRY, ERROR }

private enum class ShiftState { OFF, ON, LOCKED }
private enum class KeyStyle { LETTER, FUNCTION, ACCENT, QUIET, DANGER }

private data class KeyboardPalette(
    val background: Int,
    val key: Int,
    val functionKey: Int,
    val surface: Int,
    val text: Int,
    val secondaryText: Int,
    val accent: Int,
    val accentSoft: Int,
    val recording: Int,
    val divider: Int,
)

/**
 * Native views keep the IME independent of an Activity lifecycle. This is important on devices
 * that aggressively recreate keyboard windows and was more reliable than a ComposeView IME.
 */
class AylooInputMethodService : InputMethodService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var pendingStore: PendingCommandStore
    private var recorder: MediaRecorder? = null
    private var activeAudio: File? = null
    private var keyboardRoot: LinearLayout? = null
    private var statusView: TextView? = null
    private var orbAnimator: Animator? = null
    private val alphabetKeyViews = mutableListOf<Pair<TextView, String>>()
    private var shiftKeyView: TextView? = null
    private var repeatingKeyActive = false
    private var stopActiveRepeat: (() -> Unit)? = null

    // Session-only history: text never leaves the device and is cleared if Android stops the IME.
    private val aylooClipboard = ArrayDeque<String>()
    private var activeMode = VoiceMode.DICTATE
    private var recordingStartedAtMs = 0L
    private var stopRecording: Runnable? = null
    private var recordingTicker: Runnable? = null
    private var transientReset: Runnable? = null
    private var orbState = OrbState.IDLE
    private var status = "Ayloo"
    private var featurePanelExpanded = false
    private var symbols = false
    private var symbolPage = 0
    private var shiftState = ShiftState.OFF
    private var lastShiftTapMs = 0L
    private var numericEditor = false
    private var phoneEditor = false
    private var secureEditor = false
    private var inputType = InputType.TYPE_CLASS_TEXT
    private var inputSessionId = 0L

    private val palette: KeyboardPalette
        get() {
            val night = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
                Configuration.UI_MODE_NIGHT_YES
            return if (night) {
                KeyboardPalette(
                    background = Color.rgb(29, 30, 34),
                    key = Color.rgb(48, 50, 55),
                    functionKey = Color.rgb(61, 63, 69),
                    surface = Color.rgb(38, 40, 45),
                    text = Color.rgb(244, 245, 248),
                    secondaryText = Color.rgb(177, 181, 191),
                    accent = Color.rgb(132, 113, 255),
                    accentSoft = Color.rgb(61, 55, 94),
                    recording = Color.rgb(230, 78, 96),
                    divider = Color.argb(38, 255, 255, 255),
                )
            } else {
                KeyboardPalette(
                    background = Color.rgb(235, 238, 242),
                    key = Color.WHITE,
                    functionKey = Color.rgb(211, 217, 224),
                    surface = Color.rgb(222, 226, 232),
                    text = Color.rgb(37, 39, 45),
                    secondaryText = Color.rgb(94, 99, 110),
                    accent = Color.rgb(99, 79, 231),
                    accentSoft = Color.rgb(218, 212, 255),
                    recording = Color.rgb(210, 54, 75),
                    divider = Color.argb(35, 30, 35, 45),
                )
            }
        }

    override fun onCreate() {
        super.onCreate()
        pendingStore = PendingCommandStore(this)
        pendingStore.pending()?.let { pending ->
            activeAudio = pending.audio
            activeMode = pending.mode
            orbState = OrbState.RETRY
            status = "Saved recording ready to retry"
        }
    }

    override fun onCreateInputView(): View = LinearLayout(this).also {
        keyboardRoot = it
        refreshKeyboard()
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        inputSessionId += 1
        inputType = attribute?.inputType ?: InputType.TYPE_CLASS_TEXT
        val inputClass = inputType and InputType.TYPE_MASK_CLASS
        val variation = inputType and InputType.TYPE_MASK_VARIATION
        numericEditor = inputClass == InputType.TYPE_CLASS_NUMBER ||
            inputClass == InputType.TYPE_CLASS_DATETIME || inputClass == InputType.TYPE_CLASS_PHONE
        phoneEditor = inputClass == InputType.TYPE_CLASS_PHONE
        secureEditor = (inputClass == InputType.TYPE_CLASS_TEXT && variation in setOf(
            InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
        )) || (inputClass == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD)
        if (secureEditor && orbState == OrbState.RECORDING) cancelActiveRecording()
        symbols = false
        symbolPage = 0
        shiftState = initialShiftState()
        if (secureEditor) status = "Voice is off in password fields" else if (orbState == OrbState.IDLE) status = "Ayloo"
        refreshKeyboard()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        inputSessionId += 1
        if (orbState == OrbState.RECORDING) cancelActiveRecording()
        super.onFinishInputView(finishingInput)
    }

    override fun onUpdateSelection(
        oldSelStart: Int,
        oldSelEnd: Int,
        newSelStart: Int,
        newSelEnd: Int,
        candidatesStart: Int,
        candidatesEnd: Int,
    ) {
        super.onUpdateSelection(oldSelStart, oldSelEnd, newSelStart, newSelEnd, candidatesStart, candidatesEnd)
        if (!numericEditor && !symbols && shiftState != ShiftState.LOCKED && !repeatingKeyActive) syncAutoShift()
    }

    private fun initialShiftState(): ShiftState {
        if (inputType and InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS != 0) return ShiftState.LOCKED
        return if (cursorNeedsCaps()) ShiftState.ON else ShiftState.OFF
    }

    private fun cursorNeedsCaps(): Boolean {
        val capsFlags = TextUtils.CAP_MODE_CHARACTERS or TextUtils.CAP_MODE_WORDS or TextUtils.CAP_MODE_SENTENCES
        return (currentInputConnection?.getCursorCapsMode(inputType) ?: 0) and capsFlags != 0
    }

    private fun syncAutoShift() {
        val next = if (cursorNeedsCaps()) ShiftState.ON else ShiftState.OFF
        if (next != shiftState) {
            shiftState = next
            updateShiftUi()
        }
    }

    private fun refreshKeyboard() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post(::refreshKeyboard)
            return
        }
        val root = keyboardRoot ?: return
        stopActiveRepeat?.invoke()
        stopActiveRepeat = null
        orbAnimator?.cancel()
        alphabetKeyViews.clear()
        shiftKeyView = null
        root.removeAllViews()
        root.orientation = LinearLayout.VERTICAL
        root.setPadding(dp(4), dp(3), dp(4), dp(5))
        root.setBackgroundColor(palette.background)
        window?.window?.navigationBarColor = palette.background

        addAylooToolbar(root)
        if (orbState == OrbState.RETRY) addRetryPanel(root)
        if (featurePanelExpanded && aylooClipboard.isNotEmpty()) addClipboardStrip(root)
        when {
            numericEditor -> addNumberKeys(root)
            symbols -> addSymbolKeys(root)
            else -> addLetterKeys(root)
        }
    }

    private fun addAylooToolbar(root: LinearLayout) {
        val toolbar = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(2), 0, dp(2), dp(1))
        }
        toolbar.addView(textView("✦", 17f, palette.accent, Typeface.BOLD).apply {
            gravity = Gravity.CENTER
            contentDescription = "Ayloo"
        }, LinearLayout.LayoutParams(dp(30), dp(38)))

        addModeToggle(toolbar)

        statusView = textView(status, 11.5f, palette.secondaryText).apply {
            gravity = Gravity.CENTER_VERTICAL
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
            setPadding(dp(8), 0, dp(4), 0)
        }.also { toolbar.addView(it, LinearLayout.LayoutParams(0, dp(38), 1f)) }

        val orbEnabled = !secureEditor && orbState != OrbState.PROCESSING
        createKeyView(
            label = orbLabel(),
            textSize = if (orbState == OrbState.PROCESSING) 13f else 16f,
            style = if (orbState == OrbState.RECORDING) KeyStyle.DANGER else KeyStyle.ACCENT,
            selected = orbState == OrbState.RECORDING,
            radiusDp = 19,
            contentDescription = when (orbState) {
                OrbState.RECORDING -> "Stop voice recording"
                OrbState.PROCESSING -> "Processing voice request"
                OrbState.RETRY -> "Retry saved voice request"
                else -> if (activeMode == VoiceMode.DICTATE) "Start dictation" else "Start AI command"
            },
        ).apply {
            isEnabled = orbEnabled
            alpha = if (orbEnabled) 1f else .38f
        }.also { orb ->
            bindPress(orb, onTap = ::onOrbTapped)
            toolbar.addView(orb, LinearLayout.LayoutParams(dp(38), dp(38)).apply {
                setMargins(dp(2), 0, dp(2), 0)
            })
            animateOrb(orb)
        }

        if (aylooClipboard.isNotEmpty()) {
            val clips = createKeyView(
                label = if (featurePanelExpanded) "×" else "⋯",
                textSize = 17f,
                style = KeyStyle.QUIET,
                selected = featurePanelExpanded,
                radiusDp = 18,
                contentDescription = if (featurePanelExpanded) "Close clipboard" else "Open Ayloo clipboard",
            )
            bindPress(clips) {
                featurePanelExpanded = !featurePanelExpanded
                refreshKeyboard()
            }
            toolbar.addView(clips, LinearLayout.LayoutParams(dp(36), dp(36)).apply {
                setMargins(dp(2), 0, 0, 0)
            })
        }
        root.addView(toolbar, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(41)))
    }

    private fun addModeToggle(toolbar: LinearLayout) {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(2), dp(2), dp(2), dp(2))
            background = roundedBackground(palette.surface, dp(17).toFloat(), palette.divider)
            alpha = if (secureEditor || orbState == OrbState.RECORDING || orbState == OrbState.PROCESSING) .55f else 1f
        }
        fun segment(label: String, mode: VoiceMode, description: String) {
            val selected = activeMode == mode
            val view = textView(label, 11.5f, if (selected) palette.accent else palette.secondaryText, if (selected) Typeface.BOLD else Typeface.NORMAL).apply {
                gravity = Gravity.CENTER
                background = roundedBackground(if (selected) palette.accentSoft else Color.TRANSPARENT, dp(14).toFloat())
                contentDescription = description
                isEnabled = !secureEditor && orbState !in setOf(OrbState.RECORDING, OrbState.PROCESSING, OrbState.RETRY)
            }
            bindPress(view) { selectMode(mode) }
            container.addView(view, LinearLayout.LayoutParams(0, dp(30), 1f))
        }
        segment("Dictate", VoiceMode.DICTATE, "Use exact voice dictation")
        segment("AI", VoiceMode.COMMAND, "Use AI voice command")
        toolbar.addView(container, LinearLayout.LayoutParams(dp(118), dp(34)).apply { setMargins(dp(2), 0, dp(2), 0) })
    }

    private fun addRetryPanel(root: LinearLayout) {
        val retryRow = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), dp(1), dp(2), dp(1))
            background = roundedBackground(palette.surface, dp(10).toFloat(), palette.divider)
        }
        retryRow.addView(textView("Saved safely · retry when connected", 11.5f, palette.secondaryText).apply {
            gravity = Gravity.CENTER_VERTICAL
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }, LinearLayout.LayoutParams(0, dp(38), 1f))
        addCompactAction(retryRow, "Retry", KeyStyle.ACCENT, ::retryPending)
        addCompactAction(retryRow, "Discard", KeyStyle.QUIET, ::discardPending)
        root.addView(retryRow, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(42)).apply {
            setMargins(dp(2), dp(1), dp(2), dp(2))
        })
    }

    private fun addCompactAction(row: LinearLayout, label: String, style: KeyStyle, action: () -> Unit) {
        val view = createKeyView(label, 11.5f, style, radiusDp = 15, contentDescription = label)
        bindPress(view, onTap = action)
        row.addView(view, LinearLayout.LayoutParams(dp(64), dp(30)).apply { setMargins(dp(3), 0, 0, 0) })
    }

    private fun addClipboardStrip(root: LinearLayout) {
        val clips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        clips.addView(textView("Clipboard", 11.5f, palette.secondaryText, Typeface.BOLD).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(7), 0, dp(5), 0)
        }, LinearLayout.LayoutParams(dp(72), dp(38)))
        aylooClipboard.take(6).forEach { clip ->
            val label = clip.replace('\n', ' ').let { if (it.length > 22) it.take(22) + "…" else it }
            val chip = createKeyView(label, 11.5f, KeyStyle.QUIET, radiusDp = 15, contentDescription = "Insert $label")
            bindPress(chip) { currentInputConnection?.commitText(clip, 1) }
            clips.addView(chip, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(32)).apply {
                setMargins(dp(2), 0, dp(2), 0)
            })
        }
        val clear = createKeyView("Clear", 11f, KeyStyle.QUIET, radiusDp = 15, contentDescription = "Clear Ayloo clipboard")
        bindPress(clear) {
            aylooClipboard.clear()
            featurePanelExpanded = false
            refreshKeyboard()
        }
        clips.addView(clear, LinearLayout.LayoutParams(dp(56), dp(32)).apply { setMargins(dp(2), 0, dp(3), 0) })
        root.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            isFillViewport = true
            addView(clips)
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(40)))
    }

    private fun addLetterKeys(root: LinearLayout) {
        val rows = KeyboardLayout.letters(false)
        root.addView(row().also { top ->
            rows[0].forEach { letter -> addLetterKey(top, letter) }
        }, keyRowParams())
        root.addView(row().also { middle ->
            addSpacer(middle, .42f)
            rows[1].forEach { letter -> addLetterKey(middle, letter) }
            addSpacer(middle, .42f)
        }, keyRowParams())
        root.addView(row().also { lower ->
            shiftKeyView = addKey(
                lower,
                if (shiftState == ShiftState.LOCKED) "⇧·" else "⇧",
                weight = 1.45f,
                style = KeyStyle.FUNCTION,
                selected = shiftState != ShiftState.OFF,
                description = if (shiftState == ShiftState.LOCKED) "Caps lock on" else "Shift",
            ) { toggleShift() }
            rows[2].forEach { letter -> addLetterKey(lower, letter) }
            addKey(lower, "⌫", 1.45f, KeyStyle.FUNCTION, description = "Backspace", repeatable = true, onRelease = ::syncAutoShift) {
                backspace()
            }
        }, keyRowParams())
        addBottomRow(root)
    }

    private fun addLetterKey(row: LinearLayout, letter: String) {
        val label = letterForCurrentShift(letter)
        val view = addKey(row, label) { commitKey(letterForCurrentShift(letter)) }
        alphabetKeyViews += view to letter
    }

    private fun letterForCurrentShift(letter: String): String = if (shiftState == ShiftState.OFF) {
        letter
    } else {
        letter.uppercase(Locale.US)
    }

    /** Capitalization changes update 27 existing views instead of rebuilding the whole IME. */
    private fun updateShiftUi() {
        alphabetKeyViews.forEach { (view, letter) -> view.text = letterForCurrentShift(letter) }
        shiftKeyView?.let { shift ->
            val selected = shiftState != ShiftState.OFF
            shift.text = if (shiftState == ShiftState.LOCKED) "⇧·" else "⇧"
            shift.contentDescription = if (shiftState == ShiftState.LOCKED) "Caps lock on" else "Shift"
            applyKeyAppearance(shift, KeyStyle.FUNCTION, selected, radiusDp = 7)
        }
    }

    private fun addSymbolKeys(root: LinearLayout) {
        val rows = KeyboardLayout.symbols(symbolPage)
        addCharacterRow(root, rows[0])
        addCharacterRow(root, rows[1])
        root.addView(row().also { third ->
            addKey(third, if (symbolPage == 0) "=\\<" else "?123", 1.45f, KeyStyle.FUNCTION, description = "More symbols") {
                symbolPage = 1 - symbolPage
                refreshKeyboard()
            }
            rows[2].forEach { label -> addKey(third, label) { commitKey(label) } }
            addKey(third, "⌫", 1.45f, KeyStyle.FUNCTION, description = "Backspace", repeatable = true, onRelease = ::syncAutoShift) {
                backspace()
            }
        }, keyRowParams())
        addBottomRow(root)
    }

    private fun addNumberKeys(root: LinearLayout) {
        val numberRows = if (phoneEditor) {
            listOf(listOf("1", "2", "3"), listOf("4", "5", "6"), listOf("7", "8", "9"), listOf("+", "0", "⌫"))
        } else {
            listOf(listOf("1", "2", "3", "-"), listOf("4", "5", "6", "."), listOf("7", "8", "9", ","), listOf("0", "⌫"))
        }
        numberRows.forEachIndexed { rowIndex, labels ->
            root.addView(row().also { numberRow ->
                labels.forEach { label ->
                    if (label == "⌫") {
                        addKey(numberRow, label, style = KeyStyle.FUNCTION, description = "Backspace", repeatable = true) { backspace() }
                    } else {
                        addKey(numberRow, label, style = if (label in setOf("-", ".", ",", "+")) KeyStyle.FUNCTION else KeyStyle.LETTER) {
                            commitKey(label)
                        }
                    }
                }
                if (rowIndex == numberRows.lastIndex && labels.size == 2) {
                    addKey(numberRow, enterLabel(), style = KeyStyle.ACCENT, description = "Enter") { enter() }
                }
            }, keyRowParams(height = 50))
        }
    }

    private fun addCharacterRow(root: LinearLayout, characters: List<String>) {
        root.addView(row().also { keyRow ->
            characters.forEach { label -> addKey(keyRow, label) { commitKey(label) } }
        }, keyRowParams())
    }

    private fun addBottomRow(root: LinearLayout) {
        root.addView(row().also { bottom ->
            addKey(bottom, if (symbols) "ABC" else "?123", 1.25f, KeyStyle.FUNCTION, description = "Switch symbols") {
                symbols = !symbols
                symbolPage = 0
                refreshKeyboard()
            }
            addKey(bottom, if (emailOrUriEditor()) "@" else ",", .8f, KeyStyle.FUNCTION) {
                commitKey(if (emailOrUriEditor()) "@" else ",")
            }
            addKey(bottom, "English", 3.45f, KeyStyle.LETTER, description = "Space") { commitKey(" ") }
            addKey(bottom, ".", .8f, KeyStyle.FUNCTION) { commitKey(".") }
            addKey(bottom, "⌨", .9f, KeyStyle.FUNCTION, description = "Switch keyboard") { switchKeyboard() }
            addKey(bottom, enterLabel(), 1.2f, KeyStyle.ACCENT, description = "Enter") { enter() }
        }, keyRowParams())
    }

    private fun emailOrUriEditor(): Boolean {
        val variation = inputType and InputType.TYPE_MASK_VARIATION
        return variation == InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS ||
            variation == InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS ||
            variation == InputType.TYPE_TEXT_VARIATION_URI
    }

    private fun enterLabel(): String = when (currentInputEditorInfo?.imeOptions?.and(EditorInfo.IME_MASK_ACTION)) {
        EditorInfo.IME_ACTION_GO -> "Go"
        EditorInfo.IME_ACTION_SEARCH -> "⌕"
        EditorInfo.IME_ACTION_SEND -> "Send"
        EditorInfo.IME_ACTION_NEXT -> "Next"
        EditorInfo.IME_ACTION_DONE -> "Done"
        else -> "↵"
    }

    private fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }

    private fun keyRowParams(height: Int = 52) = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(height))

    private fun addSpacer(row: LinearLayout, weight: Float) {
        row.addView(View(this), LinearLayout.LayoutParams(0, dp(50), weight))
    }

    private fun addKey(
        row: LinearLayout,
        label: String,
        weight: Float = 1f,
        style: KeyStyle = KeyStyle.LETTER,
        selected: Boolean = false,
        description: String = label,
        repeatable: Boolean = false,
        onRelease: (() -> Unit)? = null,
        onTap: () -> Unit,
    ): TextView {
        val textSize = when {
            label.length >= 5 -> 12f
            label.length >= 3 -> 13f
            else -> 19f
        }
        val view = createKeyView(label, textSize, style, selected, radiusDp = 7, contentDescription = description)
        bindPress(view, repeatable, onRelease, onTap)
        row.addView(view, LinearLayout.LayoutParams(0, dp(48), weight).apply {
            setMargins(dp(2), dp(2), dp(2), dp(2))
        })
        return view
    }

    private fun createKeyView(
        label: String,
        textSize: Float,
        style: KeyStyle,
        selected: Boolean = false,
        radiusDp: Int,
        contentDescription: String,
    ): TextView {
        return textView(label, textSize, palette.text, if (selected) Typeface.BOLD else Typeface.NORMAL).apply {
            gravity = Gravity.CENTER
            isClickable = true
            isFocusable = false
            this.contentDescription = contentDescription
            applyKeyAppearance(this, style, selected, radiusDp)
        }
    }

    private fun applyKeyAppearance(view: TextView, style: KeyStyle, selected: Boolean, radiusDp: Int) {
        val baseColor = when (style) {
            KeyStyle.LETTER -> palette.key
            KeyStyle.FUNCTION -> if (selected) palette.accentSoft else palette.functionKey
            KeyStyle.ACCENT -> palette.accent
            KeyStyle.QUIET -> palette.surface
            KeyStyle.DANGER -> palette.recording
        }
        val textColor = when {
            style == KeyStyle.ACCENT || style == KeyStyle.DANGER -> Color.WHITE
            selected -> palette.accent
            else -> palette.text
        }
        view.setTextColor(textColor)
        view.typeface = Typeface.create("sans-serif", if (selected) Typeface.BOLD else Typeface.NORMAL)
        view.elevation = if (style == KeyStyle.LETTER) dp(1).toFloat() else 0f
        view.background = rippleBackground(baseColor, dp(radiusDp).toFloat())
    }

    private fun textView(label: String, size: Float, color: Int, typefaceStyle: Int = Typeface.NORMAL) = TextView(this).apply {
        text = label
        setTextSize(TypedValue.COMPLEX_UNIT_SP, size)
        setTextColor(color)
        includeFontPadding = false
        typeface = Typeface.create("sans-serif", typefaceStyle)
        setPadding(dp(3), 0, dp(3), 0)
    }

    private fun bindPress(
        view: TextView,
        repeatable: Boolean = false,
        onRelease: (() -> Unit)? = null,
        onTap: () -> Unit,
    ) {
        var holding = false
        var repeatCount = 0
        val repeat = object : Runnable {
            override fun run() {
                if (!holding) return
                onTap()
                repeatCount += 1
                mainHandler.postDelayed(this, if (repeatCount > 10) 30L else 42L)
            }
        }
        view.setOnTouchListener { touched, event ->
            if (!touched.isEnabled) return@setOnTouchListener true
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    holding = true
                    if (repeatable) repeatingKeyActive = true
                    touched.isPressed = true
                    touched.animate().cancel()
                    touched.animate().scaleX(.975f).scaleY(.975f).setDuration(30L).start()
                    touched.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                    touched.playSoundEffect(SoundEffectConstants.CLICK)
                    // IME keys commit on touch-down so fast alternating taps cannot be dropped.
                    onTap()
                    if (repeatable) {
                        repeatCount = 0
                        stopActiveRepeat = {
                            holding = false
                            repeatingKeyActive = false
                            mainHandler.removeCallbacks(repeat)
                        }
                        mainHandler.postDelayed(repeat, 300L)
                    }
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val slop = dp(12).toFloat()
                    val inside = event.x >= -slop && event.x <= touched.width + slop &&
                        event.y >= -slop && event.y <= touched.height + slop
                    if (!inside && holding) {
                        holding = false
                        if (repeatable) repeatingKeyActive = false
                        if (repeatable) stopActiveRepeat = null
                        touched.isPressed = false
                        mainHandler.removeCallbacks(repeat)
                        touched.animate().cancel()
                        touched.animate().scaleX(1f).scaleY(1f).setDuration(45L).start()
                        onRelease?.invoke()
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    val wasHolding = holding
                    holding = false
                    if (repeatable) repeatingKeyActive = false
                    if (repeatable) stopActiveRepeat = null
                    touched.isPressed = false
                    mainHandler.removeCallbacks(repeat)
                    touched.animate().cancel()
                    touched.animate().scaleX(1f).scaleY(1f).setDuration(45L).start()
                    if (wasHolding) onRelease?.invoke()
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    val wasHolding = holding
                    holding = false
                    if (repeatable) repeatingKeyActive = false
                    if (repeatable) stopActiveRepeat = null
                    touched.isPressed = false
                    mainHandler.removeCallbacks(repeat)
                    touched.animate().cancel()
                    touched.animate().scaleX(1f).scaleY(1f).setDuration(45L).start()
                    if (wasHolding) onRelease?.invoke()
                    true
                }
                else -> true
            }
        }
    }

    private fun roundedBackground(color: Int, radius: Float, stroke: Int? = null) = GradientDrawable().apply {
        cornerRadius = radius
        setColor(color)
        if (stroke != null) setStroke(dp(1), stroke)
    }

    private fun rippleBackground(color: Int, radius: Float): RippleDrawable {
        val content = roundedBackground(color, radius, palette.divider)
        val mask = roundedBackground(Color.WHITE, radius)
        return RippleDrawable(ColorStateList.valueOf(Color.argb(55, 255, 255, 255)), content, mask)
    }

    private fun animateOrb(view: TextView) {
        orbAnimator = when (orbState) {
            OrbState.RECORDING -> ObjectAnimator.ofPropertyValuesHolder(
                view,
                PropertyValuesHolder.ofFloat(View.SCALE_X, .88f, 1f),
                PropertyValuesHolder.ofFloat(View.SCALE_Y, .88f, 1f),
                PropertyValuesHolder.ofFloat(View.ALPHA, .72f, 1f),
            ).apply {
                duration = 650L
                repeatCount = ObjectAnimator.INFINITE
                repeatMode = ObjectAnimator.REVERSE
                start()
            }
            OrbState.PROCESSING -> ObjectAnimator.ofFloat(view, View.ROTATION, 0f, 360f).apply {
                duration = 950L
                repeatCount = ObjectAnimator.INFINITE
                start()
            }
            else -> null
        }
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun toggleShift() {
        val now = SystemClock.elapsedRealtime()
        shiftState = when (shiftState) {
            ShiftState.OFF -> ShiftState.ON
            ShiftState.ON -> if (now - lastShiftTapMs <= DOUBLE_TAP_MS) ShiftState.LOCKED else ShiftState.OFF
            ShiftState.LOCKED -> ShiftState.OFF
        }
        lastShiftTapMs = now
        updateShiftUi()
    }

    private fun onOrbTapped() {
        if (secureEditor) return
        when (orbState) {
            OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> if (hasMicPermission()) startRecording() else requestMicPermission()
            OrbState.RECORDING -> finishRecordingAndSubmit()
            OrbState.RETRY -> retryPending()
            OrbState.PROCESSING -> Unit
        }
    }

    private fun selectMode(mode: VoiceMode) {
        if (orbState == OrbState.IDLE || orbState == OrbState.SUCCESS || orbState == OrbState.ERROR) {
            activeMode = mode
            status = if (mode == VoiceMode.DICTATE) "Exact speech to text" else "Ask, rewrite or create"
            refreshKeyboard()
            scheduleIdleReset(2_000L)
        }
    }

    private fun hasMicPermission() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestMicPermission() {
        status = "Allow microphone, then tap the orb again"
        refreshKeyboard()
        startActivity(Intent(this, PermissionActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun startRecording() {
        transientReset?.let(mainHandler::removeCallbacks)
        val target = pendingStore.createFile()
        try {
            recorder = MediaRecorder(this).apply {
                setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioChannels(1)
                setAudioEncodingBitRate(96_000)
                setAudioSamplingRate(16_000)
                setOutputFile(target.absolutePath)
                prepare()
                start()
            }
            activeAudio = target
            recordingStartedAtMs = SystemClock.elapsedRealtime()
            orbState = OrbState.RECORDING
            status = listeningStatus(0L)
            refreshKeyboard()
            startRecordingTicker()
            stopRecording = Runnable { if (orbState == OrbState.RECORDING) finishRecordingAndSubmit() }.also {
                mainHandler.postDelayed(it, MAX_RECORDING_MS)
            }
        } catch (_: Exception) {
            pendingStore.discard(target)
            orbState = OrbState.ERROR
            status = "Microphone unavailable · tap to retry"
            refreshKeyboard()
        }
    }

    private fun startRecordingTicker() {
        recordingTicker?.let(mainHandler::removeCallbacks)
        recordingTicker = object : Runnable {
            override fun run() {
                if (orbState != OrbState.RECORDING) return
                val elapsed = SystemClock.elapsedRealtime() - recordingStartedAtMs
                statusView?.text = listeningStatus(elapsed)
                mainHandler.postDelayed(this, 1_000L)
            }
        }.also { mainHandler.post(it) }
    }

    private fun listeningStatus(elapsedMs: Long): String {
        val seconds = (elapsedMs / 1_000L).coerceAtMost(30L)
        val label = if (activeMode == VoiceMode.DICTATE) "Listening" else "Listening for AI"
        return "$label · 0:${seconds.toString().padStart(2, '0')}"
    }

    private fun finishRecordingAndSubmit() {
        cancelRecordingTimers()
        val audio = activeAudio
        try {
            recorder?.stop()
        } catch (_: RuntimeException) {
            pendingStore.discard(audio)
        }
        recorder?.release()
        recorder = null
        if (audio == null || !audio.exists() || audio.length() < MIN_AUDIO_BYTES) {
            pendingStore.discard(audio)
            activeAudio = null
            orbState = OrbState.ERROR
            status = "Too short · tap and speak again"
            refreshKeyboard()
            scheduleIdleReset(3_000L)
            return
        }
        submit(audio, (SystemClock.elapsedRealtime() - recordingStartedAtMs).coerceIn(1L, MAX_RECORDING_MS), activeMode)
    }

    private fun submit(audio: File, durationMs: Long = MAX_RECORDING_MS, mode: VoiceMode = activeMode) {
        val requestSessionId = inputSessionId
        pendingStore.retain(audio, durationMs, mode)
        orbState = OrbState.PROCESSING
        status = if (mode == VoiceMode.DICTATE) "Transcribing…" else "Creating answer…"
        refreshKeyboard()
        executor.execute {
            try {
                val response = CommandApi().execute(audio, durationMs, mode)
                mainHandler.post {
                    val canInsert = requestSessionId == inputSessionId && !secureEditor
                    if (mode == VoiceMode.DICTATE) {
                        if (canInsert) insertOnly(response.transcript) else saveToAylooClipboard(response.transcript)
                    } else {
                        if (canInsert) copyAndInsert(response.result) else copyOnly(response.result)
                    }
                    pendingStore.discard(audio)
                    activeAudio = null
                    orbState = OrbState.SUCCESS
                    status = when {
                        !canInsert && mode == VoiceMode.DICTATE -> "Saved in Ayloo clipboard"
                        !canInsert -> "Copied · field changed"
                        mode == VoiceMode.DICTATE -> "Inserted"
                        else -> "Inserted · copied"
                    }
                    refreshKeyboard()
                    scheduleIdleReset(2_400L)
                }
            } catch (exception: Exception) {
                mainHandler.post {
                    activeAudio = audio
                    orbState = OrbState.RETRY
                    status = exception.message ?: "Could not connect · recording saved"
                    featurePanelExpanded = false
                    refreshKeyboard()
                }
            }
        }
    }

    private fun scheduleIdleReset(delayMs: Long) {
        transientReset?.let(mainHandler::removeCallbacks)
        transientReset = Runnable {
            if (orbState == OrbState.SUCCESS || orbState == OrbState.ERROR || orbState == OrbState.IDLE) {
                orbState = OrbState.IDLE
                status = if (secureEditor) "Voice is off in password fields" else "Ayloo"
                refreshKeyboard()
            }
        }.also { mainHandler.postDelayed(it, delayMs) }
    }

    private fun cancelRecordingTimers() {
        stopRecording?.let(mainHandler::removeCallbacks)
        recordingTicker?.let(mainHandler::removeCallbacks)
        stopRecording = null
        recordingTicker = null
    }

    private fun cancelActiveRecording() {
        cancelRecordingTimers()
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        pendingStore.discard(activeAudio)
        activeAudio = null
        orbState = OrbState.IDLE
        status = if (secureEditor) "Voice is off in password fields" else "Ayloo"
        refreshKeyboard()
    }

    private fun retryPending() {
        pendingStore.pending()?.let { pending ->
            activeMode = pending.mode
            submit(pending.audio, pending.durationMs, pending.mode)
        } ?: run {
            orbState = OrbState.IDLE
            status = "No saved recording"
            refreshKeyboard()
            scheduleIdleReset(1_800L)
        }
    }

    private fun discardPending() {
        pendingStore.discard(pendingStore.pending()?.audio)
        activeAudio = null
        orbState = OrbState.IDLE
        featurePanelExpanded = false
        status = "Recording discarded"
        refreshKeyboard()
        scheduleIdleReset(1_800L)
    }

    private fun copyAndInsert(text: String) {
        copyOnly(text)
        currentInputConnection?.commitText(text, 1)
    }

    private fun copyOnly(text: String) {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("Ayloo command", text))
        saveToAylooClipboard(text)
    }

    private fun insertOnly(text: String) {
        saveToAylooClipboard(text)
        currentInputConnection?.commitText(text, 1)
    }

    private fun saveToAylooClipboard(text: String) {
        val normalized = text.trim()
        if (normalized.isEmpty()) return
        aylooClipboard.remove(normalized)
        aylooClipboard.addFirst(normalized)
        while (aylooClipboard.size > MAX_CLIPBOARD_ITEMS) aylooClipboard.removeLast()
    }

    private fun commitKey(key: String) {
        currentInputConnection?.commitText(key, 1)
        if (!symbols && shiftState == ShiftState.ON) {
            shiftState = ShiftState.OFF
            updateShiftUi()
        }
    }

    /** One tap deletes one code point; holding accelerates through text like a standard keyboard. */
    private fun backspace() {
        val connection = currentInputConnection ?: return
        connection.beginBatchEdit()
        try {
            if (!connection.deleteSurroundingTextInCodePoints(1, 0)) connection.deleteSurroundingText(1, 0)
        } finally {
            connection.endBatchEdit()
        }
    }

    private fun enter() {
        val connection = currentInputConnection ?: return
        val options = currentInputEditorInfo?.imeOptions ?: EditorInfo.IME_ACTION_NONE
        val action = options and EditorInfo.IME_MASK_ACTION
        val shouldPerformAction = action !in setOf(EditorInfo.IME_ACTION_NONE, EditorInfo.IME_ACTION_UNSPECIFIED) &&
            options and EditorInfo.IME_FLAG_NO_ENTER_ACTION == 0
        if (!shouldPerformAction || !connection.performEditorAction(action)) connection.commitText("\n", 1)
    }

    private fun switchKeyboard() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            switchToNextInputMethod(false)
        } else {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
    }

    private fun orbLabel() = when (orbState) {
        OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> "✦"
        OrbState.RECORDING -> "■"
        OrbState.PROCESSING -> "◌"
        OrbState.RETRY -> "↻"
    }

    override fun onDestroy() {
        cancelRecordingTimers()
        transientReset?.let(mainHandler::removeCallbacks)
        orbAnimator?.cancel()
        if (recorder != null) {
            runCatching { recorder?.stop() }
            recorder?.release()
            pendingStore.discard(activeAudio)
        }
        recorder = null
        executor.shutdownNow()
        super.onDestroy()
    }

    private companion object {
        const val MAX_RECORDING_MS = 30_000L
        const val MIN_AUDIO_BYTES = 1_000L
        const val MAX_CLIPBOARD_ITEMS = 8
        const val DOUBLE_TAP_MS = 420L
    }
}
