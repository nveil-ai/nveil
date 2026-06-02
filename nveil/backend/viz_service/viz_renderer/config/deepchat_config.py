# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

#:inputAreaStyle='{\"backgroundColor\": \"#ebf5ff\"}'
custom_css="""
style='width:100%;height:100%; border:0px; display:flex;padding: 15px;'
:textInput='{
    "styles": {
      "text": {"padding": "1.4em 1.5em", "color":"white"},
      "container":{"background-color":"#303030","box-shadow":"none"}
    },
    "placeholder": {"text": "Insert text here..."}
  }'
:chatStyle='{"backgroundColor": "#212121", "borderRadius": "0px"}'

:messageStyles='{
    "default": {
      "shared": {
        "outerContainer": {"backgroundColor": "transparent"},
        "innerContainer": {"backgroundColor": "transparent"},
        "bubble": {"color": "white"}
      },
      "ai": {"bubble": {"backgroundColor": "#00000021","padding":"25px"}},
      "user": {"bubble": {"backgroundColor": "transparent"}}
    }
  }'
"""

introMessage="""
:introMessage='{"text": "Hi. I am your data-viz assistant, ask me anything. You can drag-and-drop some files and I will help you generate some interesting visualizations."}'
"""

avatars="""
"""