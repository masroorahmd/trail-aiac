---
description: Hand control to the install-helper subagent to install the Trail framework into a consumer project.
argument-hint: "<absolute-path-to-consumer-project>"
---

You are now invoking the **install-helper** subagent.

The user's brief follows. Pass it through verbatim and let the
install-helper persona drive — do not pre-process, do not summarise,
do not start asking the configuration questions yourself.

```
Install the framework in: $ARGUMENTS
```

If `$ARGUMENTS` is empty, ask the user one question: *"Which consumer
project should the framework be installed into? (absolute path)"* and
wait.
