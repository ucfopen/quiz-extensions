# Change Log

## [Unreleased]

- Dockerize the application
  - Update the README to include instructions for running the application in a Docker container

## [5.0.0] - 2021-10-31

### General

- Added ability to give extensions to users in the `"invited"` enrollment state.
- Changed student list from loading 10 at at time with pagination to loading all with scrolling.
- Renamed "filter" to "search"
- Change config template to use `"staff"` rather than `"admin"` and `"student"`.

### Bugfixes

- Fixed an issue where a change to headers in the ["Get users in a course" endpoint of the Canvas API](https://canvas.instructure.com/doc/api/courses.html#method.courses.users) caused students to be displayed only if there were 10 or fewer in the course.

### Backstage

- Switched from Travis CI to GitHub Actions
- Switched from Coveralls to Codecov
- Added CanvasAPI for some API calls
- Added test for accessing from a bad domain

## [4.0.0] - 2020-03-31

### General

- Added GitHub-specific files:
  - Code owners
  - Issue template
  - Pull request template

### Bugfixes

- Fixed an issue where session cookies would be blocked due to SameSite restrictions.
  - **Note:** requires `config.py` update as shown in `config.py.template`
- Fixed an issue where Quiz Extensions would ignore changes to quiz time limits when looking for updated quizzes.
  - **Note:** requires database migration to be run with `flask db upgrade`

## [3.1.1] - 2018-12-19

### Bugfixes

- Pinned older versions of Redis and RQ to maintain compatibility.

## [3.1.0] - 2018-10-30

### General

- Added changelog
- Updated requirements versions
- Added functionality to automatically resize the LTI window
- Added XML URL to status page

### Bugfixes

- Upgraded Requests library to fix a security vulnerability

## [3.0.0] - 2017-11-21

### General

- Added background worker processes for Refresh and Update
- Allow extensions to become inactive (for when a student drops the course)
- Setup logging

### Bugfixes

- Fixed an issue with updating extensions of a student who changed roles
- Fixed an issue where clicking the name of a user wouldn't add them to the list

## [2.0.0] - 2017-03-07

### General

- Added database to track what extensions have been applied

## [1.0.0] - 2016-09-02

### General

- Initial release

[Unreleased]: https://github.com/ucfopen/quiz-extensions/compare/v5.0.0...master
[5.0.0]: https://github.com/ucfopen/quiz-extensions/compare/v4.0.0...v5.0.0
[4.0.0]: https://github.com/ucfopen/quiz-extensions/compare/v3.1.1...v4.0.0
[3.1.1]: https://github.com/ucfopen/quiz-extensions/compare/v3.1.0...v3.1.1
[3.1.0]: https://github.com/ucfopen/quiz-extensions/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/ucfopen/quiz-extensions/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/ucfopen/quiz-extensions/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/ucfopen/quiz-extensions/compare/5a01595...v1.0.0
