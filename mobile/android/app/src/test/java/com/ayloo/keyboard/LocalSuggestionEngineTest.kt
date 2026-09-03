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

    @Test
    fun neverReplacesAnUnknownNameWithUnrelatedFallbackText() {
        val suggestions = LocalSuggestionEngine.suggest("Message Naveenx")
        assertEquals(listOf(Suggestion("Naveenx", 7)), suggestions)
    }

    @Test
    fun keepsAnAlreadyCompleteWordAsSafeChoice() {
        val suggestions = LocalSuggestionEngine.suggest("help")
        assertTrue(suggestions.any { it.text == "help" && it.replaceCharacters == 4 })
        assertTrue(suggestions.none { it.text in setOf("I", "the", "to") })
    }

    @Test
    fun typedWordCannotBeTruncatedBehindCompletions() {
        val suggestions = LocalSuggestionEngine.suggest("the")
        assertTrue(suggestions.take(3).any { it.text == "the" && it.replaceCharacters == 3 })
    }

    @Test
    fun correctsCommonTranspositionAndContractionTypos() {
        assertEquals("the", LocalSuggestionEngine.suggest("teh").first().text)
        assertEquals("don't", LocalSuggestionEngine.suggest("dont").first().text)
    }

    @Test
    fun predictsAfterPunctuationWithoutDeletingPreviousText() {
        val suggestions = LocalSuggestionEngine.suggest("hello, ")
        assertTrue(suggestions.all { it.replaceCharacters == 0 })
    }

    @Test
    fun capitalizesSentenceStartPredictions() {
        val suggestions = LocalSuggestionEngine.suggest("Done. ")
        assertTrue(suggestions.all { it.text.first().isUpperCase() })
    }
}
