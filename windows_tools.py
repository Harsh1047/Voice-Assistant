import subprocess
import webbrowser

def open_notepad():
    """Open Notepad on this Windows computer."""
    subprocess.Popen(["notepad.exe"])
    return "Notepad launched."



def open_calculator():
    """Open Windows Calculator."""
    subprocess.Popen(["calc.exe"])
    return "Calculator launched."


def open_google():
    """Open Google's homepage in the default browser."""
    opened = webbrowser.open("https://www.google.com")
    return "Browser launch requested." if opened else "Could not launch browser."

TOOLS = {
    "open_notepad": open_notepad,
    "open_calculator": open_calculator,
    "open_google": open_google,
}

if __name__ == "__main__":
    action = input("Action: ").strip()

    tool = TOOLS.get(action)

    if tool is None:
        print("That action is not supported.")
    else:
        print(tool())