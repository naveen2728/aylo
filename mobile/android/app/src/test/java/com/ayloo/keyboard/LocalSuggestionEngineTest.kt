package com.ayloo.keyboard

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalSuggestionEngineTest {
    @Test
    fun completesCurrentEnglishWord() {
        val suggestions = LocalSuggestionEngine.suggest("Please hel")
        assertTrue(suggestions.any { it.text == "help" })
        assertTrue(suggestions.all { it.replaceCharacters == 3 })
    }

    @Test
    fun predictsFromPreviousWord() {
        val suggestions = LocalSuggestionEngine.suggest("thank ")
        assertEquals("you", suggestions.first().text)
        assertEquals(0, suggestions.first().replaceCharacters)
    }

    @Test
    fun preservesCapitalizationForCompletion() {
        val suggestions = LocalSuggestionEngine.suggest("Hel")
        assertTrue(suggestions.all { it.text.first().isUpperCase() })
    }
}
