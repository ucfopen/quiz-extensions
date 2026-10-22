# Contributing to Quiz Extensions

Thank you for your interest in contributing to Quiz Extensions. Even though it
was originally created by the University of Central Florida, Quiz Extensions
relies on the contributions of people like you in order to be the best it can
be. This document outlines the standards we use for various aspects of the
project, and should be followed whenever possible. If you have ideas for
additions or changes to this document, please follow the guidelines below to
submit them.

## Table of Contents

* [Reporting Bugs and Requesting Features](#reporting-bugs-and-requesting-features)
  * [Before Submitting](#before-submitting)
  * [Submitting a Bug Report](#submitting-a-bug-report)
  * [Requesting Features](#requesting-features)
* [Branching and Merging](#branching-and-merging)
  * [Forking](#forking)
  * [Master Branch](#master-branch)
  * [Dev Branches](#dev-branches)
  * [Issue Branches](#issue-branches)
  * [Releases](#releases)
  * [Pictures to really drive it home](#pictures-to-really-drive-it-home)

## Reporting Bugs and Requesting Features

### Before Submitting

Before you reporting a bug or requesting a feature, take a few moments to look
through the existing issues. Someone else may have already had the same issue
or idea. Also, check the pull requests that have been closed since you last
updated Quiz Extensions. Your issue or feature may have already been dealt with.

### Submitting a Bug Report

Once you've determined that your bug hasn't been reported or fixed already, you
can submit an issue. It's important to include as much detail as possible so
that your issue can be resolved faster. Here's a quick list of information
to include:

* Version number, date of your last pull from Github, or Git commit ID
* Detailed step-by-step to reproduce the issue
* Screenshots or screen captures showing the issue
* Severity of the issue. Is Quiz Extensions completely broken, or can you work
  around the issue in the meantime?

Before submitting, use the labels to mark the issue as a Bug.

### Requesting Features

Once you've determined that your feature hasn't been requested or implemented
already, you can submit an issue. Please take some time to flesh out the
feature as much as possible. The more work you put into the feature now, the
sooner it will be implemented. Here are some things to include:

* Why do you want this feature? What are the use cases?
* Will this feature be useful to other institutions? If so, describe how.
* How should the feature work, and what should it look like? Include wireframes
  and workflow.
* Are you able to implement this feature yourself? If not, are you available
  for consultation during the implementation process?
* How desperately do you need this feature?

Keep in mind that other contributors to this project have their own list of
priorities, so there is no guarantee that your feature will be implemented as
soon as you would like. The more universal the feature is, the more likely other
contributors will help with the implementation.

## Branching and Merging

If you are contributing code to this project, please follow the
guidelines below.

### Forking

If you are outside of UCF, you will need to fork this project in order to work
on it. Please follow the branching guidelines below. If you are familiar with
Git, but are unsure of the forking process, read the
[Forking Projects](https://guides.github.com/activities/forking/) guide.

### Master Branch

* This is the default branch.
* It always points at the latest release (thus always production ready)

### Dev Branches

* Naming Convention: `dev/v1.2.10` - a new one for every upcoming
  release version
* Issue branches merge into this branch (never master)
* When this dev branch is ready for release, it is merged into master
  and deleted

### Issue Branches

* Naming Convention: `issue/3432-add-package-json-dependency`
* The number is an issue number, and the text is a very short description of
  the issue.
* All issue branches must be tied to an issue, even in your forked version of
  the project.
* Make sure you update your forked version first, then create your issue branch
  from the current dev branch.
* After work is completed, create a pull request into the target dev branch
  (never master).
* Once the pull request is merged, the issue branch should be deleted.

### Releases

This section is mainly for the project managers, but is here for
documentation purposes.

* Naming convention: `v1.2.10` using [SEMVER](http://semver.org/)
* Each release gets a tag after it's merged into master
* Write a [release doc for Github](https://help.github.com/articles/creating-releases/)
* It is suggested that you sign release tags for extra trust
  ([git tag](https://git-scm.com/book/tr/v2/Git-Tools-Signing-Your-Work))

### Pictures to really drive it home

```Formatted
┌───────────┐  ┌───────────┐  ┌───────────┐
|           |  |           |  |           |
|  Master   |  |  Develop  |  |   Issue   |
|           |  |           |  |           |
└───────────┘  └───────────┘  └───────────┘

release   ◄──    merge   ◄──    merge

tags:     branches:    branches:
v0.0.3    ◄──  dev/v0.0.3 ◄── issue/123-fix-broken-links + issue/211
v0.0.2    ◄──  dev/v0.0.2 ◄── issue/251-rename-all-the-files + issue/222 + issue/12221
v0.0.1    ◄──  dev/v0.0.1 ◄── issue/121-get-logins-working-again
```
