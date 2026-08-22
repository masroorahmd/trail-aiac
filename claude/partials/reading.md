## Reading large files

Two thirds of a mature repository's bytes sit in a quarter of its
files. Reading one of those whole returns mostly code you will not
touch.

- **At or under __LARGE_FILE_LINES__ lines *and* __LARGE_FILE_KB__ KB:
  read the whole file.** A partial read there saves nothing and only
  narrows your view.
- **Over either threshold: read the head first, then the symbol.**
  The head is the module docstring plus the imports — roughly the
  first __HEAD_LINES__ lines — and it is not optional. A codebase
  states its invariants once, at the top, far from where they bind.
  **Both thresholds are live, because a line is not a unit of size.**
  Prose files — a context core, a persona memory, a design note —
  are written one paragraph per line, so a 500-line file can carry
  100 KB and clear a line-only threshold without ever being small.
  Check the bytes before you decide a file is short.
- **Locate by symbol, then read its neighbourhood.** Grep for the
  definition, then read a window around it. A rule that binds one
  branch is often written above the branch before it — widen the
  window before concluding a reason is absent.
- **Read the whole file anyway when the task is the whole file** — a
  review, a sweep, a refactor, any change whose correctness depends on
  sites you have not enumerated yet, or a *register* whose header says
  the whole-file read is the point. These thresholds govern sampling a
  file you need part of; there is no head of a roadmap that answers
  "what is next?".

## Reading in one round-trip

A pickup step numbers the things you must read. The numbers say
*what*, not *in what order* — and a read you sent by itself is a whole
turn spent waiting, because your prompt, your context files and the
ticket are re-sent before every single one.

- **Send independent reads together.** Every file read, and every
  Plane retrieve whose target you already know, goes out in ONE
  message. A five-file pickup is one round-trip, not five.
- **Split only where the target depends on an answer.**
  `list_comments` is what tells you which comment id to fetch, so
  `retrieve_comment` waits for it. Reading the ticket does not tell
  you where `coding.md` lives.
- **Writes stay one at a time.** A Plane comment cannot be edited and
  a state transition has an order, so you read each result before
  sending the next. This rule is about reads.
