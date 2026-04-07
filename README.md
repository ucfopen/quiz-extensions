[![Build Status](https://github.com/ucfopen/quiz-extensions/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ucfopen/quiz-extensions/actions/workflows/run-tests.yml/)
[![Coverage Status](https://codecov.io/gh/ucfopen/quiz-extensions/branch/master/graph/badge.svg?token=7MfeVsKdxc)](https://codecov.io/gh/ucfopen/quiz-extensions)
[![Join UCF Open Slack Discussions](https://badgen.net/badge/icon/ucfopen?icon=slack&label=slack&color=pink)](https://dl.ucf.edu/join-ucfopen)

A self-service LTI for faculty to easily extend time for multiple users for
all quizzes at once.

# Table of Contents

- [Installation](#installation)
  - [Download the Repository](#download-the-repository)
  - [Logs](#logs)
  - [Environment Variables](#environment-variables)
  - [Config](#config)
  - [Run Database Migrations](#run-database-migrations)
- [Proxying](#proxying)
  - [Ngrok](#ngrok)
- [LTI 1.3 Configuration and Installation](#lti-13-configuration-and-installation)
  - [Key Generation](#key-generation)
  - [Tool Registration](#tool-registration)
    - [Begin Registration](#begin-registration)
    - [Create Developer LTI Key / Get Client ID](#create-developer-lti-key--get-client-id)
    - [Finish Registration](#finish-registration)
  - [Deploy to an Account or Course](#deploy-to-an-account-or-course)
  - [Wrapping Up](#wrapping-up)
- [Code Quality and Testing](#code-quality-and-testing)
  - [Formatting and Linting](#formatting-and-linting)
  - [Testing](#testing)
- [Acknowledgements](#acknowledgements)
- [Contact Us](#contact-us)

## Installation

### Download the Repository

```sh
git clone git@github.com:ucfopen/quiz-extensions.git
```

Switch into the new directory

```sh
cd quiz-extensions
```

### Logs

Logger requires a log directory to function.

Create the directory
```sh
mkdir ./lti/logs
```

Then create the log file
```sh
touch ./lti/logs/quiz_ext.log
```

### Environment Variables

Create the .env file from the template

```sh
cp .env.template .env
```

Fill in the .env file.

The following variables NEED to be changed for the tool to function:

`API_KEY`: Your Canvas API key, for making extension/accomodation requests.
`API_URL`: The URL to your Canvas installation. You do not need to put "/api/v1", CanvasAPI handles that automatically.
`SECRET_KEY`: A secret key used by Flask for signing LTI 1.3 deployments. If you need help making a secure key, see [Create a Secret Key for Flask](https://gist.github.com/Thetwam/00db8de982d0202ece2420a87065c525) for instructions.

These variables can be changed depending on your installation, but are fine by default:

`REDIS_URL`: URI to the Redis server, do not change unless you are using an external Redis server.
`SQLALCHEMY_DATABASE_URI`: URI to the database, do not change unless you are using an external database.

### Run Database Migrations

This tool uses a database to manage LTI 1.3 keys, registrations, and deployments. Create the tables by running migrations with the following command:

```sh
make migrate-run
```

## Running Server

We use Docker to run the server. The `Makefile` contains several commands to make running and managing containers easier.

To run in attached mode, use:

```sh
make start-attached
```

To run in daemon mode, use:

```sh
make start
```

Use `make help` to see all your options!

## Proxying

When running this tool locally, you will need the app to serve over HTTPS. This can be done by creating SSL Certs or via proxying:

### Ngrok

Note: Sometimes due to firewall or network settings, you may need to use a tool such as Ngrok to have your application be reached by a third party like Canvas (usually in local development when hosting from own computer).

To do so, make sure you have Ngrok installed. Once installed you will need to follow the process to authenticate Ngrok so that you can run Ngrok with https. Go to the Ngrok site, create a free account, and it will give you an authtoken as well as a command to authenticate ngrok in your terminal.

Once Ngrok is set up, you can start the service by running the command below. This creates a new address that you will use and forwards traffic from this to the localhost docker container that you are using.

```bash
ngrok http 8000
```

## LTI 1.3 Configuration and Installation

### Key Generation

As part of the LTI 1.3 process, this tool uses a public and private keypair. To generate a new keypair, use the command below. The first time you generate keys, choose the option to create a new key set. Later, this key set will be associated with a registration of the tool into a platform.

```sh
make generate-keys
```

Take note of the ID of the key set that was created or used. You will need this value later.

If you create additional keys in the future, you may create new key sets or add the key to an existing key set. Note that currently this tool only uses the first key in a given keyset.

### Tool Registration

#### Begin Registration

To register as an LTI 1.3 tool into a platform (such as Canvas), run the following command:

```sh
make register
```

If you're using a Canvas instance hosted by Instructure, select the corresponding platform (prod, test, or beta). If you're using a self hosted instance, select "Other Canvas Platform" and copy-paste the server's url. Be sure to remove any extra paths or trailing slashes.

You will be prompted to enter a Client ID. The next section will explain how to get the Client ID from Canvas.

#### Create Developer LTI Key / Get Client ID

Go to your Canvas instance and log in with your account. Make sure you have admin privileges to create a developer key.

Now click on the Admin tab of the ribbon and click the account name where you would like to install your tool. In the navigation menu on the left, select "Developer Keys".

On the "Account" tab, click "+ Developer Key" and select "+ LTI Key". Change the key name, following the syntax: "{Your first name} - Quiz Extensions". Set the owner email to your work email.

If installing an Instructure-hosted instance of this tool (or one that is otherwise publically accessible), select "Enter URL" and paste the full URL to the LTI Config page. (e.g. https://your-tool-domain/quiz-extensions/lticonfig)

If installing a **self-hosted** instance of this tool, select "Paste JSON" in the method selection menu. Post the JSON from before (e.g. [https://use-your-unique-number-here.ngrok-free.app/quiz-extensions/lticonfig](https://ngrok.com) if running locally with ngrok) in the textbox that appears.

Save the developer key.

Enable the key by changing the State to "On".

Copy the number formatted as "1000000000XXXX" in the details column for the new key you created. This is the tool's Client ID.

#### Finish Registration

Paste the Client ID into the registration script.

Note that Client IDs must be unique for a given issuer and cannot be used multiple times. If you have already registered a Client ID, you do not need to make an additional registration and can make multiple deployments with the existing registration.

Select which key set you would like to use. Ideally, this will be the one you created earlier in the process.

### Deploy to an Account or Course

Head to the Canvas Course or Account you want to install the LTI in. Navigate to the Settings tab and click on "Apps". Here, create a new App with the blue "+ App" button and set the configuration type to "By Client ID". Paste in the number copied from before.

In the new app, click the gear icon and then click "Deployment ID". Copy this deployment ID.

Run the following command:

```sh
make deploy
```

Select which registration you'd like to use for this deployment. Ideally, it will be the one you created in the previous section.

When prompted, paste the deployment ID from Canvas.

### Wrapping up

Quiz Extensions is now configured and installed! Go to the course or account in Canvas where you installed the tool and find your tool in the Course Navigation or Account Navigation. Click on the tool to launch it.

## Code Quality and Testing

### Formatting and Linting

We use `black` for autoformatting, `isort` for import sorting, and `flake8` for linting.

To check for formatting, import sorting, and linting issues, run:

```sh
make lint-format-check
```

To automatically fix formatting and import sorting errors, run:

```sh
make lint-format
```

Linting errors will need to be fixed manually.

### Testing

In order to run the current test suite, run the command:

```sh
make test-all
```
## Acknowledgements:

- 1EdTech's [LTI 1.3 Specification](https://www.imsglobal.org/spec/lti/v1p3)
- University of Central Florida's
  - [canvasapi](https://github.com/ucfopen/canvasapi)
- [pylti1.3](https://github.com/dmitry-viskov/pylti1.3)

## Contact Us

Need help? Have an idea? Just want to say hi? Come join us on the [UCF Open Slack Channel](https://dl.ucf.edu/join-ucfopen) and join the `#quiz-extensions` channel!
