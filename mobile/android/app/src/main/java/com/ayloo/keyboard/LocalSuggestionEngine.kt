package com.ayloo.keyboard

import java.util.Locale

internal data class Suggestion(val text: String, val replaceCharacters: Int)

/** Small offline English completion model. Typed context is processed in memory and never uploaded. */
internal object LocalSuggestionEngine {
    private val commonWords = listOf(
        "the", "to", "and", "a", "of", "in", "is", "it", "you", "that", "for", "on", "with", "this", "I",
        "be", "are", "as", "at", "have", "was", "not", "but", "we", "they", "from", "by", "will", "can",
        "my", "your", "our", "about", "what", "when", "where", "how", "why", "who", "there", "here", "just",
        "do", "does", "did", "done", "make", "made", "get", "got", "go", "going", "come", "coming", "know",
        "think", "want", "need", "like", "love", "work", "working", "use", "using", "help", "please", "thanks",
        "thank", "yes", "no", "okay", "good", "great", "right", "now", "today", "tomorrow", "time", "people",
        "new", "more", "most", "some", "any", "all", "one", "two", "first", "last", "next", "back", "very",
        "really", "also", "only", "even", "well", "much", "many", "way", "thing", "things", "something",
        "because", "if", "then", "than", "so", "or", "would", "could", "should", "may", "might", "must",
        "hello", "hey", "hi", "morning", "afternoon", "evening", "message", "email", "call", "send", "share",
        "look", "see", "check", "review", "update", "create", "build", "add", "change", "remove", "start", "stop",
        "app", "website", "project", "product", "team", "user", "users", "business", "idea", "design", "keyboard",
        "voice", "text", "word", "words", "answer", "question", "information", "important", "available", "possible",
        "happy", "sorry", "sure", "welcome", "perfect", "better", "best", "easy", "quick", "ready", "free",
    )

    private val nextWords = mapOf(
        "thank" to listOf("you", "you so much", "you for"),
        "how" to listOf("are", "do", "can"),
        "what" to listOf("is", "do", "are"),
        "i" to listOf("am", "think", "want"),
        "we" to listOf("can", "are", "need"),
        "you" to listOf("can", "are", "have"),
        "can" to listOf("you", "we", "I"),
        "could" to listOf("you", "we", "be"),
        "would" to listOf("you", "be", "like"),
        "please" to listOf("check", "send", "let"),
        "let" to listOf("me", "us", "them"),
        "good" to listOf("morning", "idea", "work"),
        "looking" to listOf("forward", "good", "at"),
        "see" to listOf("you", "if", "the"),
        "need" to listOf("to", "a", "more"),
        "want" to listOf("to", "a", "you"),
        "going" to listOf("to", "well", "back"),
        "this" to listOf("is", "will", "looks"),
        "the" to listOf("app", "best", "new"),
        "for" to listOf("the", "you", "this"),
        "in" to listOf("the", "a", "this"),
        "on" to listOf("the", "this", "my"),
    )

    fun suggest(context: String): List<Suggestion> {
        val prefix = context.takeLastWhile { it.isLetter() || it == '\'' }
        val words = WORD.findAll(context).map { it.value }.toList()
        if (prefix.isNotEmpty()) {
            val normalized = prefix.lowercase(Locale.US)
            val candidates = commonWords.asSequence()
                .filter { it.lowercase(Locale.US).startsWith(normalized) && !it.equals(prefix, ignoreCase = true) }
                .distinctBy { it.lowercase(Locale.US) }
                .take(3)
                .map { word ->
                    val adjusted = if (prefix.firstOrNull()?.isUpperCase() == true) {
                        word.replaceFirstChar { it.uppercase(Locale.US) }
                    } else word
                    Suggestion(adjusted, prefix.length)
                }
                .toList()
            if (candidates.isNotEmpty()) return candidates
        }

        val lastCompleteWord = if (prefix.isEmpty()) words.lastOrNull() else words.dropLast(1).lastOrNull()
        val predicted = nextWords[lastCompleteWord?.lowercase(Locale.US)].orEmpty()
        val fallback = if (predicted.isEmpty()) listOf("I", "the", "to") else predicted
        return fallback.take(3).map { Suggestion(it, prefix.length) }
    }

    private val WORD = Regex("[A-Za-z']+")
}
