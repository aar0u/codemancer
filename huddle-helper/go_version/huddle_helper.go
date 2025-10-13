package main

import (
	"bufio"
	"os"
	"strings"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/widget"
)

func readNames(filename string) []string {
    file, err := os.Open(filename)
    if err != nil {
        return []string{}
    }
    defer file.Close()
    var names []string
    scanner := bufio.NewScanner(file)
    for scanner.Scan() {
        name := strings.TrimSpace(scanner.Text())
        if name != "" {
            names = append(names, name)
        }
    }
    return names
}

func main() {
    a := app.New()
    w := a.NewWindow("Huddle Helper")
    w.SetFixedSize(true)

    names := readNames("names.txt")
    vbox := container.NewVBox()
    vbox.Add(widget.NewLabel("List"))

    for _, name := range names {
        checkbox := widget.NewCheck(name, nil)
        xBtn := widget.NewButton("✗", nil)
        xBtnBgRed := false
        xBtn.OnTapped = func() {
            xBtnBgRed = !xBtnBgRed
            if !xBtnBgRed {
                xBtn.Importance = widget.MediumImportance
                checkbox.SetChecked(false)
                xBtn.Refresh()
            } else {
                xBtn.Importance = widget.WarningImportance
                xBtn.Refresh()
            }
        }
    row := container.New(layout.NewHBoxLayout(), checkbox, layout.NewSpacer(), xBtn)
        vbox.Add(row)
    }

    w.SetContent(container.NewPadded(vbox))
    w.Resize(fyne.NewSize(260, 400))
    w.CenterOnScreen()
    w.ShowAndRun()
}