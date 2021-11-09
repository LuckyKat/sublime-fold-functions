import sublime, sublime_plugin
import re

settings = {}

def init_plugin():
    global settings

    # Setup settings
    settings = sublime.load_settings('foldfunctions.sublime-settings')

    # I guess these reload on settings change?
    settings.clear_on_change('reload')
    settings.add_on_change('reload', init_plugin)

def plugin_loaded():
    init_plugin()

class OpenListener(sublime_plugin.EventListener):
    # fold on open
    def on_load_async(self, view):
        syntax = view.settings().get('syntax');
        foldOnOpen = bool(settings.get("fold_on_open", False))
        if (foldOnOpen and ("JavaScript" in syntax)):
            fold(view, 0)

class CursorListener(sublime_plugin.EventListener):
    # this listener checks if a folded region has been selected
    def on_selection_modified_async(self, view):
        unfold = bool(settings.get("select_to_unfold", False))
        syntax = view.settings().get('syntax');
        responsiveMode = bool(settings.get("auto_fold", False))
        # syntax should be Packages/JavaScript/JavaScript.sublime-syntax
        if (not unfold or not ("JavaScript" in syntax)):
            return

        # print("cursor", view.sel()[0])
        hasUnfolded = False

        # undocumented function :|
        foldedRegions = view.folded_regions()

        sels = view.sel()
        if responsiveMode:
            # unfold by passing cursor then fold everything
            for region in foldedRegions:
                outer = sublime.Region(region.a - 1, region.b + 1);
                hasCursor = False
                for sel in sels:
                    if sel.intersects(outer):
                        view.unfold(region)
            # 2 is for making the selection a little larger
            fold(view, 2)
        else:
            # unfold by double clicking
            for region in foldedRegions:
                inner = sublime.Region(region.a + 1, region.b - 1);
                hasCursor = view.sel()[0].contains(inner)
                if hasCursor and not hasUnfolded:
                    hasUnfolded = True
                    view.unfold(region)
                    return


def collectBraces (view):
    openBraces = []
    closedBraces = []
    # unfortunately sublime text doesn't have selectors for starting and closing braces
    # gonna have to search for the opening and closing braces myself
    # TODO: since build 1326 or so there is meta.block.js
    # edit 2016/6/11: or not.... view.find_by_selector only returns outer regions, still need to look into this

    # Sublime 3.1.1 b3176 presents punctuation.section.block.begin.js and punctuation.section.block.end.js
    bracesOpen = view.find_by_selector('punctuation.section.block.begin.js')
    bracesClosed = view.find_by_selector('punctuation.section.block.end.js')
    if bracesOpen:
        braces = bracesOpen + bracesClosed
        # we require the opening and closing braces to be in the same sequence as they appear in text
        braces.sort(key=lambda region: region.a)
    else:
        # pre build3176
        braces = view.find_by_selector('meta.brace.curly.js') + view.find_by_selector('punctuation.definition.block.js') + view.find_by_selector('punctuation.section.block.js')


    for brace in braces:
        braceStr = view.substr(brace)

        if (braceStr == "{"):
            openBraces.append(brace.a)
        elif braceStr == "}":
            region = sublime.Region(openBraces.pop(), brace.b)
            closedBraces.append(region)

    return closedBraces

def getFoldableRegion (regions, parameterIndex, view):
    for region in regions:
        if (region.a == parameterIndex):
            return region
    return 0

def fold (view, edge):
    regions = collectBraces(view)

    parameters = view.find_by_selector('punctuation.definition.parameters.end.js') + view.find_by_selector('meta.function.declaration.js punctuation.section.group.end.js') + view.find_by_selector('meta.function.parameters.js punctuation.section.group.end.js')
    closeConstructors = bool(settings.get("fold_constructors", False))
    # braceSelection: 0 = inner, 1 = outer, 2 = greedy outer
    braceSelection = int(settings.get("brace_selection", 0))
    sels = view.sel()

    # fold functions by matching parameter blocks and braces
    for parameter in parameters:
        # find the corresponding brace
        index = parameter.b
        while (index < view.size()):
            char = view.substr(sublime.Region(index, index + 1))
            index += 1
            if (char == "{"):
                # this index must correspond with one of the collected braces
                break

        region = getFoldableRegion(regions, index - 1, view)
        if (region == 0):
            # no braces found
            continue
        
        # the cursor should not be here
        hasCursor = False
        for sel in sels:
            extraSel = sublime.Region(sel.a - edge, sel.a + edge)
            hasCursor = hasCursor or region.intersects(extraSel);

        if (not hasCursor):
            # exclude braces
            foldRegion = sublime.Region(region.a + 1, region.b - 1)
            if (braceSelection == 1):
                # include braces
                foldRegion = sublime.Region(region.a, region.b)
            if (braceSelection > 1):
                # everything after the parameter list
                foldRegion = sublime.Region(parameter.b, region.b)
            view.fold(foldRegion)
    
    # fold constructors 
    if closeConstructors:
        for region in regions:
            # check if it's an object literal inside a constructor
            # the scope should end with meta.function-call.constructor.js meta.group.js meta.object-literal.js
            scope = view.scope_name(region.a + 1)
            scopeArray = scope.split()
            count = len(scopeArray)
            if (count > 2 and (scopeArray[count - 1] == "meta.object-literal.js" or scopeArray[count - 1] == "meta.mapping.js") and scopeArray[count - 2] == "meta.group.js"  and scopeArray[count - 3] == "meta.function-call.constructor.js"):
                # exclude braces
                foldRegion = sublime.Region(region.a + 1, region.b - 1)
                if (braceSelection == 1):
                    # include braces
                    foldRegion = sublime.Region(region.a, region.b)
                # the cursor should not be here
                hasCursor = False
                for sel in sels:
                    extraSel = sublime.Region(sel.a - edge, sel.a + edge)
                    hasCursor = hasCursor or foldRegion.intersects(extraSel);

                if (not hasCursor):
                    view.fold(foldRegion)

def unfold(view):
    folded_regions = view.folded_regions()
    for region in folded_regions:
        view.unfold(region)

def fold_args(view):
    def _get_char(i):
        return view.substr(sublime.Region(i, i + 1))

    def _is_function_name_char(c):
        return re.match(r'[a-zA-Z0-9_]', c)

    def _sel_range(sel):
        return range(min(sel.a, sel.b), max(sel.a, sel.b))

    for sel in view.sel():
        scope = 0
        for i in _sel_range(sel):
            prev_char = _get_char(i - 1) if i > 0 else None
            if prev_char is None:
                continue

            if scope == 0 and not _is_function_name_char(prev_char):
                continue

            char = _get_char(i)
            if char == '(':
                if scope == 0:
                    start = i
                scope += 1
            elif char == ')' and scope > 0:
                scope -= 1
                if scope == 0:
                    view.fold(sublime.Region(start + 1, i))

class UnfoldFunctionsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        unfold(self.view)

class FoldFunctionsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        fold(view, 0)

class FoldArgsCommand(sublime_plugin.TextCommand):
    def has_sel(self):
        return any(abs(sel.b - sel.a) for sel in self.view.sel())

    def run(self, edit):
        if len(self.view.folded_regions()) and not self.has_sel():
            unfold(self.view)
        else:
            fold_args(self.view)
