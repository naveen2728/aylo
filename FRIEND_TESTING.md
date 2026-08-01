# VoiceFlow Friend Testing

Share:

```text
release\VoiceFlow-3.1.0-Setup.exe
```

## What Friends Should Expect

1. Windows may show an `Unknown publisher` warning because this beta is not
   digitally signed yet. Choose `More info`, then `Run anyway`.
2. The first launch asks for an optional Groq API key. Basic dictation works
   without one. AI commands require a key from `https://console.groq.com`.
3. The API key is stored in Windows Credential Manager, not in a plain-text file.

## Controls

- Hold `Right Shift` for dictation, then release it to stop and process.
- Hold `Ctrl+Space` for an AI command, then release it to stop and process.
- Right-click the orb and choose `Start Realtime Voice Chat` to talk with AI by voice. Use `Stop Realtime Voice Chat` from the same menu to end it.
- Realtime voice uses an OpenAI API key. Set it from `Change Realtime Voice API Key...` if VoiceFlow asks for one.
- To use a mouse, enable side buttons in Settings. Back records dictation and Forward records an AI command. Hold the button while speaking, then release to process.
- If your mouse software supports blocking the original Back/Forward action, enable that so the buttons only trigger VoiceFlow.
- Press `Backspace` while recording to cancel it.
- Press `Escape` twice quickly to quit.
- Right-click the orb for VoiceFlow AI and screenshot questions.

## Useful Beta Tests

- Dictate into Notepad, a browser text box, email, and chat.
- Copy text and say: `Translate the copied text into Telugu.`
- Copy text and say: `Summarize the copied text in one sentence.`
- Copy up to 100 lines of code and request a small code edit.
- Open VoiceFlow AI, capture a screenshot, and ask what is on screen.

Hotkeys may not work inside applications running as Administrator.
