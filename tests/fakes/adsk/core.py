"""SIMULATED adsk.core: application, user interface, commands and command inputs.

Simulation only (see the package docstring). Deliberately strict where real
Fusion is strict and silent failures would hide bugs: adding two inputs with
the same id to one command raises, as does adding a toolbar control whose id
already exists in a panel.
"""

from collections import deque


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
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)
        return True

    def remove(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)
            return True
        return False

    def fire(self, args):
        for handler in list(self.handlers):
            handler.notify(args)


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


class BoolValueCommandInput(CommandInput):
    def __init__(self, registry, input_id, name, is_check_box, resource, value):
        super().__init__(registry, input_id, name)
        self.isCheckBox = is_check_box
        self.value = value


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
    def __init__(self):
        self.isShowing = False
        self.message = ""
        self.progressValue = 0
        self.cancelButtonText = "Cancel"
        self.isBackgroundTranslucencyEnabled = False
        self.wasCancelled = False
        self.shown = []

    def show(self, title, message, minimum, maximum, value=0):
        self.isShowing = True
        self.message = message
        self.progressValue = value
        self.shown.append(message)
        return True

    def hide(self):
        self.isShowing = False
        return True


class UserInterface:
    """Records every message and answers questions from scripted queues.

    ``answers``: results for messageBox calls with Yes/No-type buttons
    (default ``default_answer`` when the queue is empty). ``input_answers``:
    (value, cancelled) tuples for inputBox. ``folder_answers``: folders the
    folder dialog "chooses".
    """

    def __init__(self):
        self.messages = []  # (text, title, buttons)
        self.questions = []  # text of messageBoxes that asked something
        self.answers = deque()
        self.default_answer = DialogResults.DialogYes
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
        self.messages.append((text, title, buttons))
        if buttons == MessageBoxButtonTypes.OKButtonType:
            return DialogResults.DialogOK
        self.questions.append(text)
        return self.answers.popleft() if self.answers else self.default_answer

    def inputBox(self, prompt, title="", default_value=""):  # noqa: N802
        self.input_prompts.append(prompt)
        if self.input_answers:
            return self.input_answers.popleft()
        return ("", True)

    def createFolderDialog(self):  # noqa: N802
        return FolderDialog(self)

    def createProgressDialog(self):  # noqa: N802
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
        self.userInterface = UserInterface()
        self.activeProduct = None
        self.logs = []

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = cls()
        return cls._instance

    def log(self, message, level=None, log_type=None):
        self.logs.append((message, level))


# -- simulated user actions -------------------------------------------------------


def change_input(command, input_id, **attributes):
    """Set attributes on an input as the user would, then fire inputChanged."""
    changed = command.commandInputs.itemById(input_id)
    if changed is None:
        raise AssertionError(f"no input '{input_id}'")
    for key, value in attributes.items():
        setattr(changed, key, value)
    command.inputChanged.fire(InputChangedEventArgs(changed, command.commandInputs))
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
    command.inputChanged.fire(InputChangedEventArgs(dropdown, command.commandInputs))


def click(command, input_id):
    """Press a button (BoolValueInput used as a button)."""
    return change_input(command, input_id, value=True)


def press_ok(command):
    """Click OK: fire execute; returns the event args (check executeFailed)."""
    args = CommandEventArgs(command)
    command.execute.fire(args)
    return args
