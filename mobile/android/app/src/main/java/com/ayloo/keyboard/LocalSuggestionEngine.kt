package com.ayloo.keyboard

import java.util.Locale
import kotlin.math.abs

internal data class Suggestion(val text: String, val replaceCharacters: Int)

/**
 * Small, deterministic English completion/correction model.
 *
 * Only the short text immediately before the cursor is examined. Unknown names are always kept as
 * a safe suggestion, so choosing a chip can never replace an unmatched word with unrelated text.
 */
internal object LocalSuggestionEngine {
    private val commonWords = listOf(
        "the", "to", "and", "a", "of", "in", "is", "it", "you", "that", "for", "on", "with", "this", "I",
        "be", "are", "as", "at", "have", "was", "not", "but", "we", "they", "from", "by", "will", "can",
        "my", "your", "our", "their", "about", "what", "when", "where", "how", "why", "who", "which",
        "there", "here", "just", "do", "does", "did", "done", "make", "made", "get", "got", "go", "going",
        "come", "coming", "know", "think", "want", "need", "like", "love", "work", "working", "use", "using",
        "help", "helpful", "please", "thanks", "thank", "yes", "no", "okay", "good", "great", "right", "now",
        "today", "tomorrow", "yesterday", "time", "people", "person", "new", "more", "most", "some", "any", "all",
        "one", "two", "first", "last", "next", "back", "very", "really", "also", "only", "even", "well", "much",
        "many", "way", "thing", "things", "something", "because", "if", "then", "than", "so", "or", "would",
        "could", "should", "may", "might", "must", "hello", "hey", "hi", "morning", "afternoon", "evening",
        "message", "email", "call", "send", "sent", "share", "look", "see", "check", "review", "update", "create",
        "build", "add", "change", "remove", "start", "stop", "app", "website", "project", "product", "team", "user",
        "users", "business", "idea", "design", "keyboard", "voice", "text", "word", "words", "answer", "question",
        "information", "important", "available", "possible", "happy", "sorry", "sure", "welcome", "perfect", "better",
        "best", "easy", "quick", "ready", "free", "soon", "again", "already", "always", "never", "maybe", "still",
        "before", "after", "during", "without", "between", "into", "over", "under", "around", "through", "up", "down",
        "out", "off", "same", "different", "another", "each", "every", "both", "few", "little", "own", "other",
        "home", "office", "school", "place", "day", "week", "month", "year", "number", "name", "phone", "meeting",
        "plan", "task", "reply", "note", "details", "result", "problem", "solution", "feature", "experience", "support",
        "open", "close", "save", "copy", "paste", "download", "install", "write", "read", "talk", "speak", "tell",
        "give", "take", "keep", "find", "try", "feel", "seem", "become", "show", "ask", "move", "leave", "put",
        "clear", "correct", "complete", "simple", "small", "large", "fast", "slow", "early", "late", "kind", "nice",
        "amazing", "beautiful", "professional", "friendly", "private", "safe", "online", "offline", "mobile", "Android",
        "I'm", "I've", "I'll", "I'd", "don't", "can't", "won't", "isn't", "doesn't", "didn't", "you're", "we're",
        "they're", "that's", "it's", "let's", "shouldn't", "wouldn't", "couldn't",
    )

    private val commonTypos = mapOf(
        "teh" to "the", "adn" to "and", "taht" to "that", "thsi" to "this", "hte" to "the",
        "wiht" to "with", "woudl" to "would", "coudl" to "could", "shoudl" to "should",
        "becuase" to "because", "recieve" to "receive", "seperate" to "separate", "definately" to "definitely",
        "dont" to "don't", "cant" to "can't", "wont" to "won't", "isnt" to "isn't", "doesnt" to "doesn't",
        "didnt" to "didn't", "im" to "I'm", "ive" to "I've", "ill" to "I'll", "youre" to "you're",
        "theyre" to "they're", "thats" to "that's", "lets" to "let's", "shouldnt" to "shouldn't",
        "wouldnt" to "wouldn't", "couldnt" to "couldn't",
    )

    private val nextWords = mapOf(
        "thank" to listOf("you", "you so much", "you for"),
        "thanks" to listOf("for", "so much", "again"),
        "how" to listOf("are", "do", "can"),
        "what" to listOf("is", "do", "are"),
        "i" to listOf("am", "think", "want"),
        "i'm" to listOf("not", "going", "sure"),
        "we" to listOf("can", "are", "need"),
        "you" to listOf("can", "are", "have"),
        "can" to listOf("you", "we", "I"),
        "could" to listOf("you", "we", "be"),
        "would" to listOf("you", "be", "like"),
        "should" to listOf("be", "we", "I"),
        "please" to listOf("check", "send", "let"),
        "let" to listOf("me", "us", "them"),
        "good" to listOf("morning", "idea", "work"),
        "looking" to listOf("forward", "good", "at"),
        "see" to listOf("you", "if", "the"),
        "need" to listOf("to", "a", "more"),
        "want" to listOf("to", "a", "you"),
        "going" to listOf("to", "well", "back"),
        "this" to listOf("is", "will", "looks"),
        "that" to listOf("is", "would", "sounds"),
        "the" to listOf("app", "best", "new"),
        "for" to listOf("the", "you", "this"),
        "in" to listOf("the", "a", "this"),
        "on" to listOf("the", "this", "my"),
        "talk" to listOf("to", "about", "soon"),
        "send" to listOf("me", "it", "the"),
        "sounds" to listOf("good", "great", "like"),
        "happy" to listOf("to", "birthday", "with"),
    )

    fun suggest(context: String): List<Suggestion> {
        val prefix = context.takeLastWhile { it.isLetter() || it == '\'' }
        val words = WORD.findAll(context).map { it.value }.toList()
        if (prefix.isNotEmpty()) return suggestionsForPrefix(prefix)

        val previous = words.lastOrNull()?.lowercase(Locale.US)
        val predicted = nextWords[previous].orEmpty()
        val sentenceStart = context.isBlank() || context.trimEnd().lastOrNull() in setOf('.', '!', '?')
        val fallback = if (sentenceStart) listOf("I", "The", "We") else listOf("I", "the", "to")
        return (predicted.ifEmpty { fallback }).take(3).map { word ->
            Suggestion(if (sentenceStart) capitalizePhrase(word) else word, 0)
        }
    }

    private fun suggestionsForPrefix(prefix: String): List<Suggestion> {
        val normalized = prefix.lowercase(Locale.US)
        val alternatives = LinkedHashSet<String>()
        commonTypos[normalized]?.let(alternatives::add)
        commonWords.asSequence()
            .filter { it.lowercase(Locale.US).startsWith(normalized) && !it.equals(prefix, ignoreCase = true) }
            .take(5)
            .forEach(alternatives::add)

        if (alternatives.isEmpty() && prefix.length >= 3) {
            commonWords.asSequence()
                .filter { isEditDistanceAtMostOne(normalized, it.lowercase(Locale.US)) }
                .take(2)
                .forEach(alternatives::add)
        }

        // Put the typed text within the first two choices before truncating. Corrections/completions
        // remain useful, but a name or piece of jargon can never disappear behind three guesses.
        val candidates = LinkedHashSet<String>()
        alternatives.firstOrNull()?.let(candidates::add)
        candidates.add(prefix)
        alternatives.drop(1).forEach(candidates::add)
        return candidates.take(3).map { Suggestion(matchCase(it, prefix), prefix.length) }
    }

    private fun matchCase(candidate: String, typed: String): String = when {
        typed.all { !it.isLetter() || it.isUpperCase() } -> candidate.uppercase(Locale.US)
        typed.firstOrNull()?.isUpperCase() == true -> capitalizePhrase(candidate)
        else -> candidate
    }

    private fun capitalizePhrase(value: String): String = value.replaceFirstChar { it.uppercase(Locale.US) }

    private fun isEditDistanceAtMostOne(left: String, right: String): Boolean {
        if (left == right) return true
        if (abs(left.length - right.length) > 1) return false
        val shorter = if (left.length <= right.length) left else right
        val longer = if (left.length <= right.length) right else left
        var shortIndex = 0
        var longIndex = 0
        var edits = 0
        while (shortIndex < shorter.length && longIndex < longer.length) {
            if (shorter[shortIndex] == longer[longIndex]) {
                shortIndex += 1
                longIndex += 1
            } else {
                edits += 1
                if (edits > 1) return false
                if (shorter.length == longer.length) shortIndex += 1
                longIndex += 1
            }
        }
        if (longIndex < longer.length) edits += 1
        return edits <= 1
    }

    private val WORD = Regex("[\\p{L}']+")
}
