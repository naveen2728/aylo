package com.ayloo.keyboard

import android.Manifest
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.inputmethodservice.InputMethodService
import android.icu.text.BreakIterator
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.InputType
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat
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
    private val commandApi by lazy(LazyThreadSafetyMode.NONE) { CommandApi() }
    private val graphemeIterator by lazy(LazyThreadSafetyMode.NONE) {
        BreakIterator.getCharacterInstance(Locale.getDefault())
    }
    private lateinit var pendingStore: PendingCommandStore
    private var recorder: MediaRecorder? = null
    private var activeAudio: File? = null
    private var keyboardRoot: LinearLayout? = null
    private val alphabetKeyViews = mutableListOf<Pair<TextView, String>>()
    private var shiftKeyView: TextView? = null
    private var repeatingKeyActive = false
    private var stopActiveRepeat: (() -> Unit)? = null
    private var keyGridView: FastKeyboardView? = null
    private val suggestionViews = mutableListOf<TextView>()
    private var visibleSuggestions = emptyList<Suggestion>()
    private var suggestionRefresh: Runnable? = null

    // Session-only history: text never leaves the device and is cleared if Android stops the IME.
    private val aylooClipboard = ArrayDeque<String>()
    private var dismissedSystemClipboardText: String? = null
    private var activeMode = VoiceMode.DICTATE
    private var recordingStartedAtMs = 0L
    private var stopRecording: Runnable? = null
    private var transientReset: Runnable? = null
    private var orbState = OrbState.IDLE
    private var featurePanelExpanded = false
    private var emojiPanelExpanded = false
    private var emojiCategory = "Smileys"
    private val recentEmojis = ArrayDeque<String>()
    private var symbols = false
    private var symbolPage = 0
    private var shiftState = ShiftState.OFF
    private var lastShiftTapMs = 0L
    private var numericEditor = false
    private var phoneEditor = false
    private var secureEditor = false
    private var suggestionsAllowed = true
    private var inputType = InputType.TYPE_CLASS_TEXT
    private var inputSessionId = 0L
    private var selectionStart = -1
    private var selectionEnd = -1
    private var startRecordingAfterPermission = false
    private var permissionEditorPackage: String? = null
    private var permissionEditorFieldId = 0
    private var permissionRequestedAtMs = 0L
    private val clipboardChangeListener = ClipboardManager.OnPrimaryClipChangedListener {
        dismissedSystemClipboardText = null
    }

    private val microphonePermissionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != ACTION_MICROPHONE_PERMISSION_RESULT || !startRecordingAfterPermission) return
            startRecordingAfterPermission = intent.getBooleanExtra(EXTRA_MICROPHONE_GRANTED, false)
            if (startRecordingAfterPermission) {
                mainHandler.postDelayed(::resumeRecordingAfterPermission, 220L)
            } else {
                clearPendingMicrophoneStart()
            }
        }
    }

    private val palette: KeyboardPalette
        get() {
            val night = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
                Configuration.UI_MODE_NIGHT_YES
            val accent = resolveSystemAccent(night)
            return if (night) {
                val background = Color.rgb(24, 27, 33)
                KeyboardPalette(
                    background = background,
                    key = Color.rgb(48, 53, 63),
                    functionKey = Color.rgb(38, 43, 52),
                    surface = Color.rgb(31, 36, 44),
                    text = Color.rgb(246, 247, 251),
                    secondaryText = Color.rgb(180, 186, 198),
                    accent = accent,
                    accentSoft = blendColors(background, accent, .25f),
                    recording = Color.rgb(244, 92, 86),
                    divider = Color.TRANSPARENT,
                )
            } else {
                val background = Color.rgb(235, 238, 244)
                KeyboardPalette(
                    background = background,
                    key = Color.rgb(255, 255, 255),
                    functionKey = Color.rgb(215, 220, 230),
                    surface = Color.rgb(245, 247, 251),
                    text = Color.rgb(31, 35, 43),
                    secondaryText = Color.rgb(91, 98, 112),
                    accent = accent,
                    accentSoft = blendColors(background, accent, .18f),
                    recording = Color.rgb(210, 47, 47),
                    divider = Color.TRANSPARENT,
                )
            }
        }

    override fun onCreate() {
        super.onCreate()
        val permissionFilter = IntentFilter(ACTION_MICROPHONE_PERMISSION_RESULT)
        ContextCompat.registerReceiver(
            this,
            microphonePermissionReceiver,
            permissionFilter,
            INTERNAL_BROADCAST_PERMISSION,
            null,
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .addPrimaryClipChangedListener(clipboardChangeListener)
        pendingStore = PendingCommandStore(this)
        pendingStore.pending()?.let { pending ->
            activeAudio = pending.audio
            activeMode = pending.mode
            orbState = OrbState.RETRY
        }
    }

    override fun onCreateInputView(): View = LinearLayout(this).also {
        keyboardRoot = it
        refreshKeyboard()
    }

    override fun onWindowShown() {
        super.onWindowShown()
        if (startRecordingAfterPermission) mainHandler.postDelayed(::resumeRecordingAfterPermission, 120L)
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        inputSessionId += 1
        inputType = attribute?.inputType ?: InputType.TYPE_CLASS_TEXT
        selectionStart = attribute?.initialSelStart ?: -1
        selectionEnd = attribute?.initialSelEnd ?: -1
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
        suggestionsAllowed = inputClass == InputType.TYPE_CLASS_TEXT && !secureEditor &&
            inputType and InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS == 0 &&
            variation !in setOf(
                InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS,
                InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS,
                InputType.TYPE_TEXT_VARIATION_URI,
                InputType.TYPE_TEXT_VARIATION_FILTER,
            )
        if (secureEditor) clearPendingMicrophoneStart()
        if (secureEditor && orbState == OrbState.RECORDING) cancelActiveRecording()
        symbols = false
        symbolPage = 0
        featurePanelExpanded = false
        emojiPanelExpanded = false
        shiftState = initialShiftState()
        refreshKeyboard()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        inputSessionId += 1
        selectionStart = -1
        selectionEnd = -1
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
        selectionStart = newSelStart
        selectionEnd = newSelEnd
        if (!repeatingKeyActive) {
            if (!numericEditor && !symbols && shiftState != ShiftState.LOCKED) syncAutoShift()
            scheduleSuggestionRefresh()
        }
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
        keyGridView = null
        suggestionViews.clear()
        alphabetKeyViews.clear()
        shiftKeyView = null
        root.removeAllViews()
        root.orientation = LinearLayout.VERTICAL
        root.setPadding(dp(4), dp(3), dp(4), dp(5))
        root.setBackgroundColor(palette.background)
        window?.window?.navigationBarColor = palette.background

        if (!secureEditor) {
            addAylooToolbar(root)
        } else {
            // Keep key centers identical to normal fields while exposing no private-field tools.
            root.addView(
                View(this),
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(TOOLBAR_HEIGHT_DP)),
            )
        }
        when {
            !secureEditor && featurePanelExpanded -> addClipboardPanel(root)
            emojiPanelExpanded -> addEmojiPanel(root)
            else -> addFastKeyboard(root)
        }
    }

    private fun addAylooToolbar(root: LinearLayout) {
        val toolbar = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(1), 0, dp(1), dp(1))
        }
        val clips = createKeyView(
            label = if (featurePanelExpanded) "×" else "▣",
            textSize = 15f,
            style = KeyStyle.QUIET,
            selected = featurePanelExpanded,
            radiusDp = 16,
            contentDescription = if (featurePanelExpanded) "Close clipboard" else "Open clipboard",
        )
        bindPress(clips) {
            if (!featurePanelExpanded) syncSystemClipboard()
            featurePanelExpanded = !featurePanelExpanded
            emojiPanelExpanded = false
            refreshKeyboard()
        }
        toolbar.addView(clips, LinearLayout.LayoutParams(dp(34), dp(32)).apply {
            setMargins(dp(1), 0, dp(2), 0)
        })

        if (orbState == OrbState.RETRY) {
            val retry = createKeyView("Retry", 11.5f, KeyStyle.ACCENT, radiusDp = 16, contentDescription = "Retry voice request")
            bindPress(retry, onTap = ::retryPending)
            toolbar.addView(retry, LinearLayout.LayoutParams(0, dp(36), 1f).apply { setMargins(dp(2), 0, dp(2), 0) })
            val discard = createKeyView("Discard", 11f, KeyStyle.QUIET, radiusDp = 16, contentDescription = "Discard saved recording")
            bindPress(discard, onTap = ::discardPending)
            toolbar.addView(discard, LinearLayout.LayoutParams(0, dp(36), 1f).apply { setMargins(dp(2), 0, dp(2), 0) })
        } else {
            repeat(MAX_SUGGESTIONS) { index ->
                val suggestion = createKeyView(
                    label = "",
                    textSize = 12.5f,
                    style = KeyStyle.QUIET,
                    radiusDp = 7,
                    contentDescription = "Word suggestion ${index + 1}",
                ).apply { isEnabled = false; alpha = .35f; maxLines = 1; ellipsize = TextUtils.TruncateAt.END }
                bindPress(suggestion) { visibleSuggestions.getOrNull(index)?.let(::acceptSuggestion) }
                suggestionViews += suggestion
                toolbar.addView(suggestion, LinearLayout.LayoutParams(0, dp(36), 1f).apply {
                    setMargins(dp(1), 0, dp(1), 0)
                })
            }
        }

        addModeToggle(toolbar)

        val microphoneEnabled = !secureEditor && orbState != OrbState.PROCESSING
        toolbar.addView(
            MicrophoneButtonView(
                context = this,
                state = orbState,
                colors = MicrophoneColors(
                    idle = palette.accent,
                    recording = palette.recording,
                    processing = palette.secondaryText,
                    retry = Color.rgb(234, 134, 0),
                ),
                onPress = ::onOrbTapped,
            ).apply {
                isEnabled = microphoneEnabled
                alpha = if (microphoneEnabled) 1f else .38f
            },
            LinearLayout.LayoutParams(dp(44), dp(44)).apply { setMargins(0, 0, 0, 0) },
        )

        root.addView(toolbar, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(TOOLBAR_HEIGHT_DP)))
        scheduleSuggestionRefresh()
    }

    private fun addModeToggle(toolbar: LinearLayout) {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(1), dp(1), dp(1), dp(1))
            background = roundedBackground(palette.surface, dp(15).toFloat(), palette.divider)
            alpha = if (secureEditor || orbState in setOf(OrbState.RECORDING, OrbState.PROCESSING, OrbState.RETRY)) .55f else 1f
        }
        fun segment(label: String, mode: VoiceMode, description: String) {
            val selected = activeMode == mode
            val view = textView(label, 10.5f, if (selected) palette.accent else palette.secondaryText, if (selected) Typeface.BOLD else Typeface.NORMAL).apply {
                gravity = Gravity.CENTER
                background = roundedBackground(if (selected) palette.accentSoft else Color.TRANSPARENT, dp(13).toFloat())
                contentDescription = description
                isEnabled = !secureEditor && orbState !in setOf(OrbState.RECORDING, OrbState.PROCESSING, OrbState.RETRY)
            }
            bindPress(view) { selectMode(mode) }
            container.addView(view, LinearLayout.LayoutParams(0, dp(28), 1f))
        }
        segment("D", VoiceMode.DICTATE, "Use exact voice dictation")
        segment("AI", VoiceMode.COMMAND, "Use AI voice command")
        toolbar.addView(container, LinearLayout.LayoutParams(dp(68), dp(38)).apply { setMargins(dp(2), 0, 0, 0) })
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
            dismissedSystemClipboardText = currentSystemClipboardText()
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

    private fun addSuggestionRow(root: LinearLayout) {
        visibleSuggestions = emptyList()
        val suggestions = row().apply {
            gravity = Gravity.CENTER
            setPadding(dp(2), dp(1), dp(2), dp(1))
        }
        repeat(MAX_SUGGESTIONS) { index ->
            val view = createKeyView(
                label = "",
                textSize = 14f,
                style = KeyStyle.QUIET,
                radiusDp = 8,
                contentDescription = "Word suggestion ${index + 1}",
            ).apply { isEnabled = false; alpha = .45f }
            bindPress(view) { visibleSuggestions.getOrNull(index)?.let(::acceptSuggestion) }
            suggestionViews += view
            suggestions.addView(view, LinearLayout.LayoutParams(0, dp(36), 1f).apply {
                setMargins(dp(2), dp(1), dp(2), dp(1))
            })
        }
        root.addView(suggestions, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(40)))
        scheduleSuggestionRefresh()
    }

    private fun scheduleSuggestionRefresh() {
        suggestionRefresh?.let(mainHandler::removeCallbacks)
        if (!suggestionsAllowed || suggestionViews.isEmpty() || selectionStart != selectionEnd) {
            visibleSuggestions = emptyList()
            suggestionViews.forEach { view -> view.text = ""; view.isEnabled = false; view.alpha = .35f }
            return
        }
        suggestionRefresh = Runnable(::refreshSuggestions).also { mainHandler.postDelayed(it, SUGGESTION_DELAY_MS) }
    }

    private fun refreshSuggestions() {
        if (!suggestionsAllowed || suggestionViews.isEmpty() || selectionStart != selectionEnd) return
        val beforeCursor = currentInputConnection?.getTextBeforeCursor(MAX_SUGGESTION_CONTEXT, 0)?.toString().orEmpty()
        visibleSuggestions = LocalSuggestionEngine.suggest(beforeCursor)
        suggestionViews.forEachIndexed { index, view ->
            val suggestion = visibleSuggestions.getOrNull(index)
            view.text = suggestion?.text.orEmpty()
            view.contentDescription = suggestion?.let { "Insert ${it.text}" } ?: "No suggestion"
            view.isEnabled = suggestion != null
            view.alpha = if (suggestion != null) 1f else .35f
        }
    }

    private fun acceptSuggestion(suggestion: Suggestion) {
        val connection = currentInputConnection ?: return
        if (selectionStart != selectionEnd) return
        val before = connection.getTextBeforeCursor(1, 0)?.toString().orEmpty()
        val after = connection.getTextAfterCursor(1, 0)?.toString().orEmpty()
        val leadingSpace = suggestion.replaceCharacters == 0 && before.lastOrNull()?.let { !it.isWhitespace() } == true
        val trailingSpace = after.firstOrNull()?.let { !it.isWhitespace() && it !in PUNCTUATION } != true
        connection.beginBatchEdit()
        try {
            if (suggestion.replaceCharacters > 0 &&
                !connection.deleteSurroundingTextInCodePoints(suggestion.replaceCharacters, 0)
            ) {
                connection.deleteSurroundingText(suggestion.replaceCharacters, 0)
            }
            connection.commitText(
                buildString {
                    if (leadingSpace) append(' ')
                    append(suggestion.text)
                    if (trailingSpace) append(' ')
                },
                1,
            )
        } finally {
            connection.endBatchEdit()
        }
        syncAutoShift()
        scheduleSuggestionRefresh()
    }

    private fun addFastKeyboard(root: LinearLayout) {
        val colors = FastKeyboardColors(
            key = palette.key,
            functionKey = palette.functionKey,
            accent = palette.accent,
            selected = palette.accentSoft,
            text = palette.text,
            stroke = palette.divider,
        )
        keyGridView = FastKeyboardView(this, colors, buildFastRows()).also { view ->
            root.addView(
                view,
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(keyGridHeightDp())),
            )
        }
    }

    private fun buildFastRows(): List<List<FastKey>> = when {
        numericEditor -> buildFastNumberRows()
        symbols -> buildFastSymbolRows()
        else -> buildFastLetterRows()
    }

    private fun buildFastLetterRows(): List<List<FastKey>> {
        val letters = KeyboardLayout.letters(false)
        val top = letters[0].map(::fastLetter)
        val middle = buildList {
            add(FastKey("", .42f, spacer = true))
            letters[1].forEach { add(fastLetter(it)) }
            add(FastKey("", .42f, spacer = true))
        }
        val lower = buildList {
            add(
                FastKey(
                    label = if (shiftState == ShiftState.LOCKED) "⇧·" else "⇧",
                    weight = 1.45f,
                    style = if (shiftState == ShiftState.OFF) FastKeyStyle.FUNCTION else FastKeyStyle.SELECTED,
                    description = if (shiftState == ShiftState.LOCKED) "Caps lock on" else "Shift",
                    pressOnDown = true,
                    onPress = ::toggleShift,
                ),
            )
            letters[2].forEach { add(fastLetter(it)) }
            add(fastBackspace())
        }
        return listOf(top, middle, lower, fastBottomRow())
    }

    private fun fastLetter(letter: String) = FastKey(
        label = letterForCurrentShift(letter),
        onPress = { commitKey(letterForCurrentShift(letter)) },
    )

    private fun buildFastSymbolRows(): List<List<FastKey>> {
        val rows = KeyboardLayout.symbols(symbolPage)
        val top = rows[0].map(::fastCharacter)
        val middle = rows[1].map(::fastCharacter)
        val lower = buildList {
            add(
                FastKey(
                    label = if (symbolPage == 0) "=\\<" else "?123",
                    weight = 1.45f,
                    style = FastKeyStyle.FUNCTION,
                    description = "More symbols",
                    pressOnDown = true,
                    onPress = {
                        symbolPage = 1 - symbolPage
                        keyGridView?.updateRows(buildFastRows())
                    },
                ),
            )
            rows[2].forEach { add(fastCharacter(it)) }
            add(fastBackspace())
        }
        return listOf(top, middle, lower, fastBottomRow())
    }

    private fun buildFastNumberRows(): List<List<FastKey>> {
        val inputClass = inputType and InputType.TYPE_MASK_CLASS
        val decimal = inputType and InputType.TYPE_NUMBER_FLAG_DECIMAL != 0
        val signed = inputType and InputType.TYPE_NUMBER_FLAG_SIGNED != 0
        val labels = when {
            phoneEditor -> listOf(
                listOf("1", "2", "3", "⌫"),
                listOf("4", "5", "6", "+"),
                listOf("7", "8", "9", "*"),
                listOf("#", "0", ",", enterLabel()),
            )
            inputClass == InputType.TYPE_CLASS_DATETIME -> listOf(
                listOf("1", "2", "3", "⌫"),
                listOf("4", "5", "6", "/"),
                listOf("7", "8", "9", ":"),
                listOf("-", "0", ".", enterLabel()),
            )
            else -> listOf(
                listOf("1", "2", "3", "⌫"),
                listOf("4", "5", "6", if (decimal) "." else ""),
                listOf("7", "8", "9", if (signed) "-" else ""),
                listOf("", "0", "", enterLabel()),
            )
        }
        return labels.mapIndexed { rowIndex, row ->
            row.map { label ->
                when {
                    label.isEmpty() -> FastKey("", spacer = true)
                    label == "⌫" -> fastBackspace(weight = 1f)
                    rowIndex == labels.lastIndex && label == enterLabel() -> FastKey(
                        label,
                        style = FastKeyStyle.ACCENT,
                        description = "Enter",
                        onPress = ::enter,
                    )
                    else -> fastCharacter(
                        label,
                        if (label in setOf("-", ".", ",", "+", "*", "#", "/", ":")) FastKeyStyle.FUNCTION else FastKeyStyle.LETTER,
                    )
                }
            }
        }
    }

    private fun fastCharacter(label: String, style: FastKeyStyle = FastKeyStyle.LETTER) = FastKey(
        label = label,
        style = style,
        onPress = { commitKey(label) },
    )

    private fun fastBackspace(weight: Float = 1.45f) = FastKey(
        label = "⌫",
        weight = weight,
        style = FastKeyStyle.FUNCTION,
        description = "Backspace",
        repeatable = true,
        pressOnDown = true,
        onPress = {
            repeatingKeyActive = true
            backspace()
        },
        onRelease = {
            repeatingKeyActive = false
            syncAutoShift()
            scheduleSuggestionRefresh()
        },
    )

    private fun fastBottomRow(): List<FastKey> = listOf(
        FastKey(
            label = if (symbols) "ABC" else "?123",
            weight = 1.3f,
            style = FastKeyStyle.FUNCTION,
            description = "Switch symbols",
            pressOnDown = true,
            onPress = {
                symbols = !symbols
                symbolPage = 0
                keyGridView?.updateRows(buildFastRows())
                scheduleSuggestionRefresh()
            },
        ),
        FastKey(
            label = if (emailOrUriEditor()) "@" else ",",
            weight = 1f,
            style = FastKeyStyle.FUNCTION,
            description = if (emailOrUriEditor()) "At sign; hold for emoji" else "Comma; hold for emoji",
            alternateLabel = "☺",
            onPress = { commitKey(if (emailOrUriEditor()) "@" else ",") },
            onLongPress = {
                keyGridView?.runAfterPointersReleased(::openEmojiPanel) ?: openEmojiPanel()
            },
        ),
        FastKey("English", 3.3f, description = "Space", onPress = { commitKey(" ") }),
        FastKey(".", 1f, FastKeyStyle.FUNCTION, onPress = { commitKey(".") }),
        FastKey("⌨", 1f, FastKeyStyle.FUNCTION, "Switch keyboard", pressOnDown = true, onPress = ::switchKeyboard),
        FastKey(enterLabel(), 1.4f, FastKeyStyle.ACCENT, "Enter", onPress = ::enter),
    )

    private fun openEmojiPanel() {
        emojiPanelExpanded = true
        featurePanelExpanded = false
        refreshKeyboard()
    }

    private fun syncSystemClipboard() {
        val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = manager.primaryClip ?: return
        for (index in 0 until clip.itemCount.coerceAtMost(3)) {
            val value = clip.getItemAt(index).text?.toString() ?: continue
            if (value != dismissedSystemClipboardText) saveToAylooClipboard(value)
        }
    }

    private fun currentSystemClipboardText(): String? {
        val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        return manager.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.text?.toString()
    }

    private fun addClipboardPanel(root: LinearLayout) {
        val panel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val header = row().apply { gravity = Gravity.CENTER_VERTICAL }
        addCompactAction(header, "ABC", KeyStyle.ACCENT) {
            featurePanelExpanded = false
            refreshKeyboard()
        }
        header.addView(textView("Session clipboard", 13f, palette.text, Typeface.BOLD).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(9), 0, dp(4), 0)
        }, LinearLayout.LayoutParams(0, dp(38), 1f))
        addCompactAction(header, "Clear", KeyStyle.QUIET) {
            dismissedSystemClipboardText = currentSystemClipboardText()
            aylooClipboard.clear()
            refreshKeyboard()
        }
        panel.addView(header, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(40)))

        val entries = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(2), 0, dp(2), dp(2)) }
        if (aylooClipboard.isEmpty()) {
            entries.addView(textView("Copy text, or create something with Ayloo, then open this panel.", 13f, palette.secondaryText).apply {
                gravity = Gravity.CENTER
                textAlignment = View.TEXT_ALIGNMENT_CENTER
                setPadding(dp(24), dp(20), dp(24), dp(20))
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(122)))
        } else {
            aylooClipboard.forEach { value ->
                val label = value.replace('\n', ' ').let { if (it.length > 70) it.take(70) + "…" else it }
                val item = createKeyView(label, 13f, KeyStyle.QUIET, radiusDp = 9, contentDescription = "Insert clipboard item")
                item.gravity = Gravity.CENTER_VERTICAL
                item.maxLines = 2
                item.ellipsize = TextUtils.TruncateAt.END
                item.setPadding(dp(12), dp(4), dp(12), dp(4))
                bindPress(item) {
                    currentInputConnection?.commitText(value, 1)
                    scheduleSuggestionRefresh()
                }
                entries.addView(item, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(46)).apply {
                    setMargins(0, dp(2), 0, dp(2))
                })
            }
        }
        panel.addView(ScrollView(this).apply {
            isVerticalScrollBarEnabled = false
            addView(entries)
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(panel, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(keyGridHeightDp())))
    }

    private fun addEmojiPanel(root: LinearLayout) {
        val panel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val header = row().apply { gravity = Gravity.CENTER_VERTICAL }
        val categoryContent = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        addCompactAction(header, "ABC", KeyStyle.ACCENT) {
            emojiPanelExpanded = false
            refreshKeyboard()
        }
        val categories = listOf(
            "Recent" to "◷",
            "Smileys" to "😀",
            "People" to "👋",
            "Nature" to "🌿",
            "Food" to "🍕",
            "Travel" to "🚗",
            "Objects" to "💡",
            "Symbols" to "♥",
        )
        categories.forEach { (category, icon) ->
            val button = createKeyView(
                icon,
                17f,
                KeyStyle.QUIET,
                selected = emojiCategory == category,
                radiusDp = 15,
                contentDescription = "$category emojis",
            )
            bindPress(button) {
                emojiCategory = category
                refreshKeyboard()
            }
            categoryContent.addView(button, LinearLayout.LayoutParams(dp(48), dp(32)).apply { setMargins(dp(2), 0, dp(2), 0) })
        }
        header.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(categoryContent)
        }, LinearLayout.LayoutParams(0, dp(40), 1f))
        val delete = createKeyView("⌫", 17f, KeyStyle.QUIET, radiusDp = 15, contentDescription = "Backspace")
        bindPress(
            delete,
            repeatable = true,
            onRelease = {
                repeatingKeyActive = false
                syncAutoShift()
                scheduleSuggestionRefresh()
            },
        ) {
            repeatingKeyActive = true
            backspace()
        }
        header.addView(delete, LinearLayout.LayoutParams(dp(52), dp(32)).apply { setMargins(dp(2), 0, dp(2), 0) })
        panel.addView(header, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(40)))

        val emojis = if (emojiCategory == "Recent") {
            recentEmojis.toList().ifEmpty { EmojiCatalog.categories.getValue("Smileys") }
        } else {
            EmojiCatalog.categories[emojiCategory].orEmpty()
        }.take(32)
        val grid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        emojis.chunked(8).forEach { emojiRow ->
            grid.addView(row().also { row ->
                emojiRow.forEach { emoji ->
                    val button = createKeyView(emoji, 21f, KeyStyle.QUIET, radiusDp = 8, contentDescription = "Insert emoji")
                    bindPress(button) { insertEmoji(emoji) }
                    row.addView(button, LinearLayout.LayoutParams(0, dp(40), 1f).apply {
                        setMargins(dp(2), dp(1), dp(2), dp(1))
                    })
                }
                repeat(8 - emojiRow.size) { addSpacer(row, 1f) }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(42)))
        }
        panel.addView(grid, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(panel, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(keyGridHeightDp())))
    }

    private fun insertEmoji(emoji: String) {
        currentInputConnection?.commitText(emoji, 1)
        recentEmojis.remove(emoji)
        recentEmojis.addFirst(emoji)
        while (recentEmojis.size > MAX_RECENT_EMOJIS) recentEmojis.removeLast()
        scheduleSuggestionRefresh()
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
        keyGridView?.let { grid ->
            grid.updateRows(buildFastRows())
            return
        }
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
        EditorInfo.IME_ACTION_PREVIOUS -> "Prev"
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
        view.background = instantKeyBackground(baseColor, dp(radiusDp).toFloat())
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
                    if (repeatable) {
                        onTap()
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
                    if (wasHolding) {
                        touched.performClick()
                        if (!repeatable) onTap()
                        onRelease?.invoke()
                    }
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    val wasHolding = holding
                    holding = false
                    if (repeatable) repeatingKeyActive = false
                    if (repeatable) stopActiveRepeat = null
                    touched.isPressed = false
                    mainHandler.removeCallbacks(repeat)
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

    private fun instantKeyBackground(color: Int, radius: Float): StateListDrawable {
        val pressed = Color.rgb(
            (Color.red(color) * .78f).toInt(),
            (Color.green(color) * .78f).toInt(),
            (Color.blue(color) * .78f).toInt(),
        )
        return StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed), roundedBackground(pressed, radius, palette.divider))
            addState(intArrayOf(), roundedBackground(color, radius, palette.divider))
        }
    }

    private fun keyGridHeightDp(): Int {
        val configuration = resources.configuration
        if (configuration.orientation == Configuration.ORIENTATION_LANDSCAPE) return 168
        return when {
            configuration.screenHeightDp in 1..640 -> 196
            configuration.screenHeightDp >= 800 -> 216
            else -> 208
        }
    }

    private fun resolveSystemAccent(night: Boolean): Int {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val colorResource = if (night) android.R.color.system_accent1_300 else android.R.color.system_accent1_600
            runCatching { resources.getColor(colorResource, theme) }.getOrNull()?.let { return it }
        }
        return if (night) Color.rgb(150, 126, 255) else Color.rgb(98, 72, 214)
    }

    private fun blendColors(base: Int, overlay: Int, overlayAmount: Float): Int {
        val amount = overlayAmount.coerceIn(0f, 1f)
        return Color.rgb(
            (Color.red(base) * (1f - amount) + Color.red(overlay) * amount).toInt(),
            (Color.green(base) * (1f - amount) + Color.green(overlay) * amount).toInt(),
            (Color.blue(base) * (1f - amount) + Color.blue(overlay) * amount).toInt(),
        )
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
            refreshKeyboard()
        }
    }

    private fun hasMicPermission() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestMicPermission() {
        startRecordingAfterPermission = true
        permissionEditorPackage = currentInputEditorInfo?.packageName
        permissionEditorFieldId = currentInputEditorInfo?.fieldId ?: 0
        permissionRequestedAtMs = SystemClock.elapsedRealtime()
        startActivity(Intent(this, PermissionActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun resumeRecordingAfterPermission() {
        if (!startRecordingAfterPermission) return
        if (SystemClock.elapsedRealtime() - permissionRequestedAtMs > PERMISSION_RESULT_TIMEOUT_MS) {
            clearPendingMicrophoneStart()
            return
        }
        if (!hasMicPermission()) {
            clearPendingMicrophoneStart()
            return
        }
        if (secureEditor) {
            clearPendingMicrophoneStart()
            return
        }
        if (currentInputConnection == null) return
        val editor = currentInputEditorInfo ?: return
        if (editor.packageName != permissionEditorPackage || editor.fieldId != permissionEditorFieldId) {
            clearPendingMicrophoneStart()
            return
        }
        if (orbState == OrbState.IDLE || orbState == OrbState.SUCCESS || orbState == OrbState.ERROR) {
            clearPendingMicrophoneStart()
            startRecording()
        }
    }

    private fun clearPendingMicrophoneStart() {
        startRecordingAfterPermission = false
        permissionEditorPackage = null
        permissionEditorFieldId = 0
        permissionRequestedAtMs = 0L
    }

    private fun startRecording() {
        transientReset?.let(mainHandler::removeCallbacks)
        val target = pendingStore.createFile()
        try {
            @Suppress("DEPRECATION")
            val nextRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(this) else MediaRecorder()
            recorder = nextRecorder.apply {
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
            refreshKeyboard()
            stopRecording = Runnable { if (orbState == OrbState.RECORDING) finishRecordingAndSubmit() }.also {
                mainHandler.postDelayed(it, MAX_RECORDING_MS)
            }
        } catch (_: Exception) {
            pendingStore.discard(target)
            orbState = OrbState.ERROR
            refreshKeyboard()
        }
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
        refreshKeyboard()
        executor.execute {
            try {
                val response = commandApi.execute(audio, durationMs, mode)
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
                    refreshKeyboard()
                    scheduleIdleReset(2_400L)
                }
            } catch (error: CommandRequestException) {
                mainHandler.post {
                    if (error.retryable) {
                        activeAudio = audio
                        orbState = OrbState.RETRY
                    } else {
                        pendingStore.discard(audio)
                        activeAudio = null
                        orbState = OrbState.ERROR
                        scheduleIdleReset(3_000L)
                    }
                    featurePanelExpanded = false
                    refreshKeyboard()
                }
            } catch (_: Exception) {
                mainHandler.post {
                    activeAudio = audio
                    orbState = OrbState.RETRY
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
                refreshKeyboard()
            }
        }.also { mainHandler.postDelayed(it, delayMs) }
    }

    private fun cancelRecordingTimers() {
        stopRecording?.let(mainHandler::removeCallbacks)
        stopRecording = null
    }

    private fun cancelActiveRecording() {
        cancelRecordingTimers()
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        pendingStore.discard(activeAudio)
        activeAudio = null
        orbState = OrbState.IDLE
        refreshKeyboard()
    }

    private fun retryPending() {
        pendingStore.pending()?.let { pending ->
            activeMode = pending.mode
            submit(pending.audio, pending.durationMs, pending.mode)
        } ?: run {
            orbState = OrbState.IDLE
            refreshKeyboard()
            scheduleIdleReset(1_800L)
        }
    }

    private fun discardPending() {
        pendingStore.discard(pendingStore.pending()?.audio)
        activeAudio = null
        orbState = OrbState.IDLE
        featurePanelExpanded = false
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
        scheduleSuggestionRefresh()
    }

    /** Deletes selections or one complete grapheme; holding accelerates like a standard keyboard. */
    private fun backspace() {
        val connection = currentInputConnection ?: return
        val selectionKnown = selectionStart >= 0 && selectionEnd >= 0
        val hasSelection = if (selectionKnown) {
            selectionStart != selectionEnd
        } else {
            !connection.getSelectedText(0).isNullOrEmpty()
        }
        var deletedUnits = 0
        val handled = if (hasSelection) {
            val collapsed = minOf(selectionStart, selectionEnd).coerceAtLeast(0)
            connection.commitText("", 1).also { success ->
                if (success && selectionKnown) {
                    selectionStart = collapsed
                    selectionEnd = collapsed
                }
            }
        } else {
            val lastUnit = connection.getTextBeforeCursor(1, 0)?.toString().orEmpty()
            if (lastUnit.length == 1 && lastUnit[0].code in 0x20..0x7e) {
                deletedUnits = 1
                connection.deleteSurroundingText(1, 0)
            } else {
                val beforeCursor = connection.getTextBeforeCursor(32, 0)?.toString().orEmpty()
                if (beforeCursor.isNotEmpty()) {
                    graphemeIterator.setText(beforeCursor)
                    val previousBoundary = graphemeIterator.preceding(beforeCursor.length)
                    val utf16Units = if (previousBoundary == BreakIterator.DONE) 1 else beforeCursor.length - previousBoundary
                    deletedUnits = utf16Units.coerceAtLeast(1)
                    connection.deleteSurroundingText(utf16Units.coerceAtLeast(1), 0)
                } else {
                    false
                }
            }
        }
        if (handled && selectionKnown && deletedUnits > 0) {
            selectionStart = (selectionStart - deletedUnits).coerceAtLeast(0)
            selectionEnd = selectionStart
        }
        if (!handled) {
            connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DEL))
            connection.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_DEL))
        }
        if (!repeatingKeyActive) scheduleSuggestionRefresh()
    }

    private fun enter() {
        val connection = currentInputConnection ?: return
        val options = currentInputEditorInfo?.imeOptions ?: EditorInfo.IME_ACTION_NONE
        val action = options and EditorInfo.IME_MASK_ACTION
        val shouldPerformAction = action !in setOf(EditorInfo.IME_ACTION_NONE, EditorInfo.IME_ACTION_UNSPECIFIED) &&
            options and EditorInfo.IME_FLAG_NO_ENTER_ACTION == 0
        if (!shouldPerformAction || !connection.performEditorAction(action)) connection.commitText("\n", 1)
        scheduleSuggestionRefresh()
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
        OrbState.PROCESSING -> "…"
        OrbState.RETRY -> "↻"
    }

    override fun onDestroy() {
        runCatching { unregisterReceiver(microphonePermissionReceiver) }
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .removePrimaryClipChangedListener(clipboardChangeListener)
        cancelRecordingTimers()
        transientReset?.let(mainHandler::removeCallbacks)
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
        val PUNCTUATION = setOf('.', ',', '!', '?', ':', ';', ')', ']', '}')
        const val MAX_RECORDING_MS = 30_000L
        const val PERMISSION_RESULT_TIMEOUT_MS = 90_000L
        const val MIN_AUDIO_BYTES = 1_000L
        const val MAX_CLIPBOARD_ITEMS = 8
        const val DOUBLE_TAP_MS = 420L
        const val MAX_SUGGESTIONS = 3
        const val MAX_SUGGESTION_CONTEXT = 96
        // Debounce predictions so rapid typing never competes with the touch/input path.
        const val SUGGESTION_DELAY_MS = 45L
        const val TOOLBAR_HEIGHT_DP = 44
        const val MAX_RECENT_EMOJIS = 32
    }
}
