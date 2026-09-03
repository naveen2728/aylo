package com.ayloo.keyboard

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class KeyboardLayoutTest {
    @Test
    fun qwertyRowsRemainFamiliar() {
        assertEquals(listOf(10, 9, 7), KeyboardLayout.letters(false).map { it.size })
        assertEquals("qwertyuiop", KeyboardLayout.letters(false)[0].joinToString(""))
        assertEquals("ASDFGHJKL", KeyboardLayout.letters(true)[1].joinToString(""))
    }

    @Test
    fun symbolPagesAreCompleteAndDistinct() {
        assertEquals(listOf(10, 10, 7), KeyboardLayout.symbols(0).map { it.size })
        assertEquals(listOf(10, 10, 7), KeyboardLayout.symbols(1).map { it.size })
        assertTrue("₹" in KeyboardLayout.symbols(0).flatten())
        assertTrue("/" in KeyboardLayout.symbols(0).flatten())
        assertTrue("€" in KeyboardLayout.symbols(1).flatten())
        assertTrue("\\" in KeyboardLayout.symbols(1).flatten())
    }

    @Test
    fun invalidSymbolPageIsSafelyClamped() {
        assertEquals(KeyboardLayout.symbols(0), KeyboardLayout.symbols(-1))
        assertEquals(KeyboardLayout.symbols(1), KeyboardLayout.symbols(99))
    }
}
