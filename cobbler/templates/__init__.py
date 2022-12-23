"""
Package that contains built-in templates and rendering logic from Cheetah and Jinja, as well as their abstraction layer.

Cobbler uses Cheetah templates for lots of stuff, but there's some additional magic around that to deal with
snippets/etc. (And it's not spelled wrong!)
"""

# SPDX-License-Identifier: GPL-2.0-or-later
# SPDX-FileCopyrightText: Copyright 2006-2009, Red Hat, Inc and Others
# SPDX-FileCopyrightText: Michael DeHaan <michael.dehaan AT gmail>

import logging
import os
import os.path
import re
from typing import Optional, Union, TextIO, List, Dict, TYPE_CHECKING

from cobbler.utils import filesystem_helpers

if TYPE_CHECKING:
    from cobbler.api import CobblerAPI


class BaseTemplateProvider:
    """
    TODO
    """

    template_language = "generic"
    """
    Identifier for the template type. 
    """

    def __init__(self, api: CobblerAPI):
        """
        TODO

        :param api: TODO
        """
        self.api = api
        self.logger = logging.getLogger()

    @property
    def template_type_available(self) -> bool:
        """
        Returns whether the template type can be used or should be disabled.

        :return: True in case the template provider can be used, in all other cases False.
        """
        raise NotImplementedError(
            '"template_type_available" must be implemented to be a valid template provider!'
        )

    def render(self, raw_data: str, search_table: dict) -> str:
        """
        Render data_input back into a file.

        :param raw_data: Is the template code which is not rendered into the result.
        :param search_table: is a dict of metadata keys and values (though results are always returned)
        :return: The rendered Template.
        """
        raise NotImplementedError(
            '"render" must be implemented to be a valid template provider'
        )


class Templar:
    """
    Wrapper to encapsulate all logic of the template providers.
    """

    def __init__(self, api: CobblerAPI):
        """
        Constructor

        :param api: The main API instance which is used by the current running server.
        """
        self.api = api
        self.last_errors = []
        self.logger = logging.getLogger()
        self.__loaded_template_providers: Dict[str, BaseTemplateProvider] = {}

    def __load_template_providers(self):
        pass

    def __detect_template_type(self, template_type: str, lines: List[str]) -> str:
        if template_type is None:
            raise ValueError('"template_type" can\'t be "None"!')

        if not isinstance(template_type, str):
            raise TypeError('"template_type" must be of type "str"!')

        if template_type not in ("default", "jinja2", "cheetah"):
            return "# ERROR: Unsupported template type selected!"

        if template_type == "default":
            if self.api.settings().default_template_type:
                template_type = self.api.settings().default_template_type
            else:
                template_type = "cheetah"

        if len(lines) > 0 and lines[0].find("#template=") == 0:
            # Pull the template type out of the first line and then drop it and rejoin them to pass to the template
            # language
            template_type = lines[0].split("=")[1].strip().lower()
            del lines[0]
            raw_data = "\n".join(lines)

        return template_type

    @staticmethod
    def __save_template_to_disk(out_path: str, data_out: str):
        filesystem_helpers.mkdir(os.path.dirname(out_path))
        with open(out_path, "w+", encoding="UTF-8") as file_descriptor:
            file_descriptor.write(data_out)

    @staticmethod
    def __replace_at_variables(data_out: str, search_table: dict) -> str:
        """
        string replacements for @@xyz@@ in data_out with prior regex lookups of keys
        """
        regex = r"@@[\S]*?@@"
        regex_matches = re.finditer(regex, data_out, re.MULTILINE)
        matches = {
            match.group() for match_num, match in enumerate(regex_matches, start=1)
        }
        for match in matches:
            data_out = data_out.replace(match, search_table[match.strip("@@")])
        return data_out

    def __enrich_http_server_to_search_table(self, search_table: dict):
        """
        Now apply some magic post-filtering that is used by "cobbler import" and some other places. Forcing folks to
        double escape things would be very unwelcome.
        """
        http_port = search_table.get("http_port", "80")
        server = search_table.get("server", self.api.settings().server)
        if http_port not in (80, "80"):
            repstr = f"{server}:{http_port}"
        else:
            repstr = server
        search_table["http_server"] = repstr

    def render(
        self,
        data_input: Union[TextIO, str],
        search_table: dict,
        out_path: Optional[str],
        template_type="default",
    ) -> str:
        """
        Render data_input back into a file.

        :param data_input: is either a str or a TextIO object.
        :param search_table: is a dict of metadata keys and values.
        :param out_path: Optional parameter which (if present), represents the target path to write the result into.
        :param template_type: May currently be "cheetah" or "jinja2". "default" looks in the settings.
        :return: The rendered template.
        """

        if not isinstance(data_input, str):
            raw_data = data_input.read()
        else:
            raw_data = data_input
        lines = raw_data.split("\n")

        # TODO: Remove first line of the template if the template type is in the file header
        template_type = self.__detect_template_type(template_type, lines)

        template_provider = self.__loaded_template_providers[template_type]
        data_out = template_provider.render(raw_data, search_table)

        self.__enrich_http_server_to_search_table(search_table)
        data_out = self.__replace_at_variables(data_out, search_table)

        # remove leading newlines which apparently breaks AutoYAST ?
        if data_out.startswith("\n"):
            data_out = data_out.lstrip()

        # if requested, write the data out to a file
        if out_path is not None:
            self.__save_template_to_disk(out_path, data_out)

        return data_out
