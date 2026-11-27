"""SIMULATED adsk.core: application, user interface, commands and command inputs.

Simulation only (see the package docstring). Deliberately strict where real
Fusion is strict and silent failures would hide bugs: adding two inputs with
the same id to one command raises, as does adding a toolbar control whose id
already exists in a panel; events hold their handlers weakly; input values
have Fusion's types; and the UI may only be used from the thread that
created the Application ("Fusion's main thread"). Custom events fired from
any thread are queued and only delivered by ``Application.process_events``,
which a test calls on the main thread, as Fusion's message loop would.
"""

import queue
import threading
import time
import weakref
from collections import deque


# -- Fusion's main thread -------------------------------------------------------

_MAIN = {"thread": threading.get_ident(), "violations": []}


def _on_main_thread(what):
    """Record and refuse a UI call made from a thread other than Fusion's main thread."""
    if threading.get_ident() != _MAIN["thread"]:
        _MAIN["violations"].append(f"{what} called from thread {threading.current_thread().name}")
        raise RuntimeError(f"Fusion API '{what}' called from a worker thread")


# -- enums --------------------------------------------------------------------


class DropDownStyles:
    LabeledIconDropDownStyle = 0
    CheckBoxDropDownStyle = 1
    TextListDropDownStyle = 2


class MessageBoxButtonTypes:
    OKButtonType = 0
    OKCancelButtonType = 1
    RetryCancelButtonType = 2
    YesNoButtonType = 3
    YesNoCancelButtonType = 4


class DialogResults:
    DialogError = -1
    DialogOK = 0
    DialogCancel = 1
    DialogNo = 2
    DialogYes = 3


class LogLevels:
    InfoLogLevel = 0
    WarningLogLevel = 1
    ErrorLogLevel = 2


# -- events -------------------------------------------------------------------


class Event:
    """Holds handlers by weak reference, as Fusion does: an add-in must keep its own."""

    def __init__(self):
        self._refs = []

    @property
    def handlers(self):
        return [h for h in (ref() for ref in self._refs) if h is not None]

    def add(self, handler):
        if handler in self.handlers:
            return False
        self._refs.append(weakref.ref(handler))
        return True

    def remove(self, handler):
        for ref in list(self._refs):
            if ref() is handler:
                self._refs.remove(ref)
                return True
        return False

    def fire(self, args):
        for handler in self.handlers:
            handler.notify(args)


class CustomEvent(Event):
    def __init__(self, event_id):
        super().__init__()
        self.eventId = event_id


class CustomEventHandler:
    def __init__(self):
        pass


class CustomEventArgs:
    def __init__(self, event, additional_info):
        self.firingEvent = event
        self.additionalInfo = additional_info


class ValidateInputsEventHandler:
    def __init__(self):
        pass


class ValidateInputsEventArgs:
    def __init__(self, command, inputs):
        self.firingEvent = None
        self.inputs = inputs
        self.areInputsValid = True


class CommandCreatedEventHandler:
    def __init__(self):
        pass


class InputChangedEventHandler:
    def __init__(self):
        pass


class CommandEventHandler:
    def __init__(self):
        pass


class CommandCreatedEventArgs:
    def __init__(self, command):
        self.command = command


class InputChangedEventArgs:
    def __init__(self, changed_input, inputs):
        self.input = changed_input
        self.inputs = inputs


class CommandEventArgs:
    def __init__(self, command):
        self.command = command
        self.executeFailed = False
        self.executeFailedMessage = ""


# -- command inputs -----------------------------------------------------------


class CommandInput:
    # Real Fusion raises when a deleted input is used; so does this stand-in,
    # so a stale reference kept after deleteMe() can't pass a test.
    _ALWAYS_USABLE = frozenset({"isValid", "id", "deleteMe"})

    def __getattribute__(self, name):
        if not name.startswith("_") and name not in CommandInput._ALWAYS_USABLE:
            if not object.__getattribute__(self, "__dict__").get("isValid", True):
                raise RuntimeError(f"input '{object.__getattribute__(self, 'id')}' was deleted and can't be used")
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if not name.startswith("_") and name not in CommandInput._ALWAYS_USABLE:
            if not self.__dict__.get("isValid", True):
                raise RuntimeError(f"input '{self.__dict__.get('id')}' was deleted and can't be changed")
        object.__setattr__(self, name, value)

    def __init__(self, registry, input_id, name):
        self._registry = registry
        self.id = input_id
        self.name = name
        self.isVisible = True
        self.isEnabled = True
        self.isFullWidth = False
        self.tooltip = ""
        self.isValid = True
        self.parentList = None

    def deleteMe(self):  # noqa: N802
        if not self.isValid:
            raise RuntimeError(f"input '{self.id}' was already deleted")
        self.isValid = False
        self._registry.pop(self.id, None)
        if self.parentList is not None and self in self.parentList:
            self.parentList.remove(self)
        return True


class StringValueCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, value):
        super().__init__(registry, input_id, name)
        self.value = value
        self.isPassword = False
        self.isReadOnly = False

    def __setattr__(self, name, value):
        # Fusion's StringValueCommandInput.value is a str; anything else raises.
        if name == "value" and not isinstance(value, str):
            raise TypeError(f"StringValueCommandInput.value must be str, not {type(value).__name__}")
        super().__setattr__(name, value)


class BoolValueCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, is_check_box, resource, value):
        super().__init__(registry, input_id, name)
        self.isCheckBox = is_check_box
        self.value = value

    def __setattr__(self, name, value):
        if name == "value" and not isinstance(value, bool):
            raise TypeError(f"BoolValueCommandInput.value must be bool, not {type(value).__name__}")
        super().__setattr__(name, value)


class TextBoxCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, text, rows, read_only):
        super().__init__(registry, input_id, name)
        self.text = text
        self.numRows = rows
        self.isReadOnly = read_only

    @property
    def formattedText(self):  # noqa: N802
        return self.text


class ListItem:
    def __init__(self, owner, name, selected, icon):
        self._owner = owner
        self.name = name
        self._selected = False
        self.icon = icon
        self.isSelected = selected

    @property
    def isSelected(self):  # noqa: N802
        return self._selected

    @isSelected.setter
    def isSelected(self, value):  # noqa: N802
        value = bool(value)
        if value and self._owner.single_select:
            for item in self._owner.items:
                if item is not self:
                    item._selected = False
        self._selected = value


class ListItems:
    def __init__(self, single_select):
        self.single_select = single_select
        self.items = []

    def add(self, name, is_selected, icon=""):
        item = ListItem(self, name, False, icon)
        self.items.append(item)
        item.isSelected = is_selected
        return item

    def item(self, index):
        return self.items[index]

    @property
    def count(self):
        return len(self.items)

    def clear(self):
        self.items = []
        return True

    def __iter__(self):
        return iter(list(self.items))


class DropDownCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, style):
        super().__init__(registry, input_id, name)
        self.dropDownStyle = style
        self.listItems = ListItems(single_select=style != DropDownStyles.CheckBoxDropDownStyle)

    @property
    def selectedItem(self):  # noqa: N802
        for item in self.listItems.items:
            if item.isSelected:
                return item
        return None


class TableCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, columns, ratio):
        super().__init__(registry, input_id, name)
        self.numberOfColumns = columns
        self.columnRatio = ratio
        self.cells = {}
        self.maximumVisibleRows = 4
        self.columnSpacing = 0
        self.rowSpacing = 0

    def addCommandInput(self, command_input, row, column, row_span=0, column_span=0):  # noqa: N802
        if not command_input.isValid:
            raise RuntimeError("can't add a deleted input to a table")
        self.cells[(row, column)] = command_input
        return True

    def clear(self):
        # As in Fusion: rows are detached, the inputs themselves survive.
        self.cells = {}
        return True

    @property
    def rowCount(self):  # noqa: N802
        return len({row for row, _ in self.cells})


class GroupCommandInput(CommandInput):
    def __init__(self, registry, input_id, name):
        super().__init__(registry, input_id, name)
        self.isExpanded = True
        self.isEnabledCheckBoxDisplayed = False
        self.children = CommandInputs(registry)


class CommandInputs:
    """Inputs of one command. Ids are unique across the whole command, as in Fusion."""

    def __init__(self, registry=None):
        self._registry = registry if registry is not None else {}
        self.items = []

    def _add(self, command_input):
        if command_input.id in self._registry:
            raise RuntimeError(f"an input with id '{command_input.id}' already exists in this command")
        self._registry[command_input.id] = command_input
        self.items.append(command_input)
        command_input.parentList = self.items
        return command_input

    def addGroupCommandInput(self, input_id, name):  # noqa: N802
        return self._add(GroupCommandInput(self._registry, input_id, name))

    def addStringValueInput(self, input_id, name, initial_value=""):  # noqa: N802
        return self._add(StringValueCommandInput(self._registry, input_id, name, initial_value))

    def addBoolValueInput(self, input_id, name, is_check_box, resource_folder="", initial_value=False):  # noqa: N802
        return self._add(BoolValueCommandInput(self._registry, input_id, name, is_check_box, resource_folder, initial_value))

    def addTextBoxCommandInput(self, input_id, name, formatted_text, num_rows, is_read_only):  # noqa: N802
        return self._add(TextBoxCommandInput(self._registry, input_id, name, formatted_text, num_rows, is_read_only))

    def addDropDownCommandInput(self, input_id, name, drop_down_style):  # noqa: N802
        return self._add(DropDownCommandInput(self._registry, input_id, name, drop_down_style))

    def addTableCommandInput(self, input_id, name, number_of_columns, column_ratio):  # noqa: N802
        return self._add(TableCommandInput(self._registry, input_id, name, number_of_columns, column_ratio))

    def itemById(self, input_id):  # noqa: N802
        return self._registry.get(input_id)

    @property
    def count(self):
        return len(self.items)

    def item(self, index):
        return self.items[index]


# -- commands -------------------------------------------------------------------


class Command:
    def __init__(self, definition):
        self.parentCommandDefinition = definition
        self.commandInputs = CommandInputs()
        self.isAutoExecute = True
        self.isAutoTerminate = True
        self.inputChanged = Event()
        self.execute = Event()
        self.destroy = Event()
        self.validateInputs = Event()
        self.isTerminated = False


class CommandDefinition:
    def __init__(self, collection, def_id, name, tooltip, resource_folder):
        self._collection = collection
        self.id = def_id
        self.name = name
        self.tooltip = tooltip
        self.resourceFolder = resource_folder
        self.commandCreated = Event()
        self.isValid = True

    def deleteMe(self):  # noqa: N802
        self.isValid = False
        self._collection.items.pop(self.id, None)
        return True


class CommandDefinitions:
    def __init__(self):
        self.items = {}

    def itemById(self, def_id):  # noqa: N802
        return self.items.get(def_id)

    def addButtonDefinition(self, def_id, name, tooltip, resource_folder=""):  # noqa: N802
        if def_id in self.items:
            raise RuntimeError(f"command definition '{def_id}' already exists")
        definition = CommandDefinition(self, def_id, name, tooltip, resource_folder)
        self.items[def_id] = definition
        return definition

    @property
    def count(self):
        return len(self.items)


# -- toolbars -------------------------------------------------------------------


class ToolbarControl:
    def __init__(self, controls, control_id, definition):
        self._controls = controls
        self.id = control_id
        self.commandDefinition = definition
        self.isValid = True
        self.isVisible = True
        self.isPromoted = False
        self.isPromotedByDefault = False

    def deleteMe(self):  # noqa: N802
        self.isValid = False
        self._controls.items = [c for c in self._controls.items if c is not self]
        return True


class ToolbarControls:
    def __init__(self):
        self.items = []

    def addCommand(self, definition, control_id="", position_id="", is_before=True):  # noqa: N802
        control_id = control_id or definition.id
        if self.itemById(control_id):
            raise RuntimeError(f"a control with id '{control_id}' already exists in this panel")
        control = ToolbarControl(self, control_id, definition)
        self.items.append(control)
        return control

    def itemById(self, control_id):  # noqa: N802
        for control in self.items:
            if control.id == control_id:
                return control
        return None

    @property
    def count(self):
        return len(self.items)

    def item(self, index):
        return self.items[index]


class ToolbarPanel:
    def __init__(self, panel_id, name):
        self.id = panel_id
        self.name = name
        self.controls = ToolbarControls()


class ToolbarPanels:
    def __init__(self, panels=()):
        self.items = list(panels)

    def itemById(self, panel_id):  # noqa: N802
        for panel in self.items:
            if panel.id == panel_id:
                return panel
        return None

    @property
    def count(self):
        return len(self.items)

    def item(self, index):
        return self.items[index]


class Workspace:
    def __init__(self, workspace_id, panels):
        self.id = workspace_id
        self.toolbarPanels = panels


class Workspaces:
    def __init__(self, workspaces=()):
        self.items = list(workspaces)

    def itemById(self, workspace_id):  # noqa: N802
        for workspace in self.items:
            if workspace.id == workspace_id:
                return workspace
        return None


# -- dialogs --------------------------------------------------------------------


class FolderDialog:
    def __init__(self, ui):
        self._ui = ui
        self.title = ""
        self.folder = ""
        self.initialDirectory = ""

    def showDialog(self):  # noqa: N802
        if self._ui.folder_answers:
            self.folder = self._ui.folder_answers.popleft()
            return DialogResults.DialogOK
        return DialogResults.DialogCancel


class ProgressDialog:
    """``show(title, message, minimumValue, maximumValue, delay)``: the last one is a
    delay in seconds before the dialog appears, not a value. ``wasCancelled``
    becomes True when the user presses Cancel (``press_cancel`` in tests)."""

    def __init__(self):
        object.__setattr__(self, "_ready", False)
        self.isShowing = False
        self.message = ""
        self.title = ""
        self.progressValue = 0
        self.minimumValue = 0
        self.maximumValue = 0
        self.cancelButtonText = "Cancel"
        self.isCancelButtonShown = True
        self.isBackgroundTranslucencyEnabled = False
        self.wasCancelled = False
        self.shown = []
        self.messages = []
        object.__setattr__(self, "_ready", True)

    def __setattr__(self, name, value):
        if self.__dict__.get("_ready"):
            _on_main_thread(f"ProgressDialog.{name}")
            if name == "message":
                self.messages.append(value)
        object.__setattr__(self, name, value)

    def show(self, title, message, minimum, maximum, delay=0):
        _on_main_thread("ProgressDialog.show")
        for label, value in (("minimumValue", minimum), ("maximumValue", maximum), ("delay", delay)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"ProgressDialog.show {label} must be an int, not {type(value).__name__}")
        self.isShowing = True
        self.title = title
        self.message = message
        self.minimumValue, self.maximumValue = minimum, maximum
        self.progressValue = minimum
        self.shown.append(message)
        return True

    def hide(self):
        _on_main_thread("ProgressDialog.hide")
        self.isShowing = False
        return True

    # test helper
    def press_cancel(self):
        if not self.isShowing:
            raise AssertionError("the progress dialog isn't showing, so Cancel can't be pressed")
        self.wasCancelled = True


class UserInterface:
    """Records every message and answers questions from scripted queues.

    ``answers``: results for messageBox calls with Yes/No-type buttons. A
    question with no scripted answer is recorded in ``unscripted`` and gets
    ``DialogNo``, the cautious answer; the test harness fails any test that
    leaves unscripted questions or unused answers. ``input_answers``:
    (value, cancelled) tuples for inputBox. ``folder_answers``: folders the
    folder dialog "chooses".
    """

    def __init__(self):
        self.messages = []  # (text, title, buttons)
        self.questions = []  # text of messageBoxes that asked something
        self.answers = deque()
        self.unscripted = []
        self.input_answers = deque()
        self.input_prompts = []
        self.folder_answers = deque()
        self.progress_dialogs = []
        self.commandDefinitions = CommandDefinitions()
        utilities = ToolbarPanel("SolidUtilitiesAddinsPanel", "ADD-INS")
        scripts = ToolbarPanel("SolidScriptsAddinsPanel", "Scripts")
        self.allToolbarPanels = ToolbarPanels([utilities, scripts])
        self.workspaces = Workspaces([Workspace("FusionSolidEnvironment", ToolbarPanels([utilities, scripts]))])

    def messageBox(self, text, title="", buttons=MessageBoxButtonTypes.OKButtonType, icon=0):  # noqa: N802
        _on_main_thread("messageBox")
        self.messages.append((text, title, buttons))
        # Simulation of a modal message box that keeps Fusion's message loop
        # running, so other events are delivered while it is open (assumed
        # possible in real Fusion; see README). One-shot: set by a test.
        while_open, self.while_message_box_open = getattr(self, "while_message_box_open", None), None
        if while_open is not None:
            while_open()
        if buttons == MessageBoxButtonTypes.OKButtonType:
            return DialogResults.DialogOK
        self.questions.append(text)
        if self.answers:
            return self.answers.popleft()
        self.unscripted.append(text)
        return DialogResults.DialogNo

    def inputBox(self, prompt, title="", default_value=""):  # noqa: N802
        _on_main_thread("inputBox")
        self.input_prompts.append(prompt)
        if self.input_answers:
            return self.input_answers.popleft()
        return ("", True)

    def createFolderDialog(self):  # noqa: N802
        return FolderDialog(self)

    def createProgressDialog(self):  # noqa: N802
        _on_main_thread("createProgressDialog")
        dialog = ProgressDialog()
        self.progress_dialogs.append(dialog)
        return dialog

    # test helpers ------------------------------------------------------------

    def texts(self):
        return [text for text, _, _ in self.messages]

    def open_command(self, def_id):
        """Simulate the user clicking the button: create a command, fire commandCreated."""
        definition = self.commandDefinitions.itemById(def_id)
        if definition is None:
            raise AssertionError(f"no command definition '{def_id}'")
        command = Command(definition)
        definition.commandCreated.fire(CommandCreatedEventArgs(command))
        return command


class Application:
    _instance = None

    def __init__(self):
        # The thread that creates the Application plays Fusion's main thread.
        _MAIN["thread"] = threading.get_ident()
        _MAIN["violations"] = []
        self.userInterface = UserInterface()
        self.activeProduct = None
        self.logs = []
        self._custom_events = {}
        self._queue = queue.Queue()

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = cls()
        return cls._instance

    @property
    def thread_violations(self):
        """UI calls made from a thread other than the main one (each one raised)."""
        return list(_MAIN["violations"])

    def log(self, message, level=None, log_type=None):
        _on_main_thread("Application.log")
        self.logs.append((message, level))

    # -- custom events ---------------------------------------------------------

    def registerCustomEvent(self, event_id):  # noqa: N802
        _on_main_thread("registerCustomEvent")
        if event_id in self._custom_events:
            raise RuntimeError(f"custom event '{event_id}' is already registered")
        event = CustomEvent(event_id)
        self._custom_events[event_id] = event
        return event

    def unregisterCustomEvent(self, event_id):  # noqa: N802
        _on_main_thread("unregisterCustomEvent")
        return self._custom_events.pop(event_id, None) is not None

    def fireCustomEvent(self, event_id, additional_info=""):  # noqa: N802
        """Safe from any thread. Queued: handlers run later, in process_events()."""
        if event_id not in self._custom_events:
            return False
        self._queue.put((event_id, additional_info))
        return True

    @property
    def registered_custom_events(self):
        return sorted(self._custom_events)

    def process_events(self, timeout=0.0, until=None):
        """Deliver queued custom events on this (the main) thread, like Fusion's message loop.

        Without *until*: deliver what is queued, waiting up to *timeout* s for
        more. With *until*: keep delivering until ``until()`` is true; raise
        TimeoutError after *timeout* s. Returns the number delivered.
        """
        _on_main_thread("process_events")
        deadline = time.monotonic() + timeout
        delivered = 0
        while True:
            if until is not None and until():
                return delivered
            remaining = deadline - time.monotonic()
            if remaining <= 0 and (until is not None or self._queue.empty()):
                if until is not None:
                    raise TimeoutError(f"condition not met within {timeout} s ({delivered} events delivered)")
                return delivered
            try:
                event_id, info = self._queue.get(timeout=max(0.0, min(remaining, 0.05)))
            except queue.Empty:
                if until is None and remaining <= 0:
                    return delivered
                continue
            event = self._custom_events.get(event_id)
            if event is not None:  # unregistered since it was fired: dropped, as in Fusion
                event.fire(CustomEventArgs(event, info))
                delivered += 1


# -- simulated user actions -------------------------------------------------------


def _user_changed(command, changed):
    # Fusion fires inputChanged, then validateInputs, after a user edit.
    if command.isTerminated:
        raise AssertionError("the dialog has closed")
    command.inputChanged.fire(InputChangedEventArgs(changed, command.commandInputs))
    command.validateInputs.fire(ValidateInputsEventArgs(command, command.commandInputs))


def change_input(command, input_id, **attributes):
    """Set attributes on an input as the user would, then fire inputChanged and validateInputs."""
    changed = command.commandInputs.itemById(input_id)
    if changed is None:
        raise AssertionError(f"no input '{input_id}'")
    for key, value in attributes.items():
        setattr(changed, key, value)
    _user_changed(command, changed)
    return changed


def select_item(command, input_id, name):
    """Select a dropdown item by name, then fire inputChanged."""
    dropdown = command.commandInputs.itemById(input_id)
    for item in dropdown.listItems:
        if item.name == name:
            item.isSelected = True
            break
    else:
        raise AssertionError(f"'{name}' is not in '{input_id}'")
    _user_changed(command, dropdown)


def click(command, input_id):
    """Press a button (BoolValueInput used as a button)."""
    return change_input(command, input_id, value=True)


def _terminate(command):
    command.isTerminated = True
    command.destroy.fire(CommandEventArgs(command))


def press_ok(command):
    """Click OK: fire execute; unless executeFailed was set, the command ends (destroy).

    Returns the event args (check executeFailed).
    """
    if command.isTerminated:
        raise AssertionError("the dialog has closed")
    args = CommandEventArgs(command)
    command.execute.fire(args)
    if not args.executeFailed:
        _terminate(command)
    return args


def press_cancel(command):
    """Close the dialog with Cancel: the command ends (destroy) without execute."""
    if command.isTerminated:
        raise AssertionError("the dialog has closed")
    _terminate(command)
