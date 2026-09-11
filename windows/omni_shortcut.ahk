; OmniReader AutoHotkey v2 Script
; Shortcut: Alt + Escape
; Copies highlighted text to clipboard and speaks it with omnisay

!Esc::
{
    ; Save current clipboard
    oldClip := A_Clipboard
    A_Clipboard := ""

    ; Copy selected text
    Send("^c")
    if !ClipWait(0.5)
    {
        ; If nothing was selected, restore and read clipboard directly
        A_Clipboard := oldClip
        Run("omnisay -c", , "Hide")
        return
    }

    ; Speak selection
    Run("omnisay -c", , "Hide")
    
    ; Restore clipboard after delay
    Sleep(500)
    A_Clipboard := oldClip
}
