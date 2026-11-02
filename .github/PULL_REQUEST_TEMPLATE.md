<!-- Thanks for sending a patch. -->

**What this changes**

<!-- One or two sentences. What was wrong, or what is missing? -->

**Why**

<!-- What goes wrong today without it? A concrete failure beats a description
     of the code. -->

**Testing**

<!--
Please include a test, and please check it fails before your change.
Every defect found in this library so far has been in code with 100% line
coverage, because the suite mocks the network: it proves the library builds the
request it intended, not that the result is right. A test which passes with and
without your fix is worse than none, because it looks like protection.

If the behaviour can only be established against the live API, say so and say
what you observed and when. That is a perfectly good answer.
-->

- [ ] Added a test, and watched it fail before the change
- [ ] `make test` passes
- [ ] Documentation updated, if this changes anything a user can see

**Anything else**

<!-- Behaviour changes, things you were unsure about, decisions you would like
     a second opinion on. Uncertainty stated plainly is more useful than
     confidence that turns out to be misplaced. -->
