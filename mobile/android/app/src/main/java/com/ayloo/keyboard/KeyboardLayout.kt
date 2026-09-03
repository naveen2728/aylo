package com.ayloo.keyboard

/** Stable keyboard maps kept separate from rendering so layouts can be regression-tested. */
internal object KeyboardLayout {
    private val lowerLetters = listOf(
        listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
        listOf("a", "s", "d", "f", "g", "h", "j", "k", "l"),
        listOf("z", "x", "c", "v", "b", "n", "m"),
    )

    private val symbols = listOf(
        listOf(
            listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
            listOf("@", "#", "₹", "_", "%", "&", "-", "+", "(", ")"),
            listOf("=", "\\", "<", ">", "*", "!", "?"),
        ),
        listOf(
            listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
            listOf("~", "`", "|", "•", "√", "π", "÷", "×", "§", "∆"),
            listOf("{", "}", "©", "®", "™", "[", "]"),
        ),
    )

    fun letters(uppercase: Boolean): List<List<String>> = if (uppercase) {
        lowerLetters.map { row -> row.map(String::uppercase) }
    } else {
        lowerLetters
    }

    fun symbols(page: Int): List<List<String>> = symbols[page.coerceIn(0, symbols.lastIndex)]
}
