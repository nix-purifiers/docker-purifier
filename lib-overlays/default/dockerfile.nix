# SPDX-License-Identifier: MIT
{ lib }:
text:
let
  lines = lib.splitString "\n" (
    builtins.replaceStrings [ "\\\r\n" "\\\n" "\r\n" "\t" ] [ " " " " "\n" " " ] text
  );
  tokens = line: builtins.filter (word: word != "") (lib.splitString " " line);
  result =
    lib.foldl'
      (
        state: line:
        let
          words = tokens line;
          command = if words == [ ] then "" else lib.toUpper (builtins.head words);
          args = lib.drop 1 words;
          source = if args == [ ] then "" else builtins.head args;
          external = ref: lib.toLower ref != "scratch" && !(builtins.elem (lib.toLower ref) state.stages);
          from = lib.findFirst (word: lib.hasPrefix "--from=" word) null args;
          copy = if from == null then null else lib.removePrefix "--from=" from;
        in
        if command == "FROM" then
          {
            refs = state.refs ++ lib.optional (external source) source;
            stages = state.stages ++ [
              (
                if builtins.length args == 3 then
                  lib.toLower (builtins.elemAt args 2)
                else
                  toString (builtins.length state.stages)
              )
            ];
          }
        else if
          builtins.elem command [
            "COPY"
            "ADD"
          ]
          && copy != null
          && builtins.match "[0-9]+" copy == null
          && external copy
        then
          state // { refs = state.refs ++ [ copy ]; }
        else
          state
      )
      {
        refs = [ ];
        stages = [ ];
      }
      lines;
in
lib.sort builtins.lessThan (lib.unique result.refs)
