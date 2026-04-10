from Crypto.PublicKey import RSA
from flask import Flask
from sqlalchemy.exc import IntegrityError


def register_cli(app: Flask):
    @app.cli.command("generate_keys")
    def generate_keys():
        from models import Key, KeySet, db

        def get_keyset():
            all_keysets = KeySet.query.all()

            print(
                "Would you like to create your new key in a new key set or use an existing one?\n"
                "  1 - Create a new key set\n"
                f"  2 - Use an existing key set ({len(all_keysets)} available)"
            )
            new_or_old = input("Selection number: ")

            if new_or_old == "1":
                print("Creating new key set...")
                selected_keyset = KeySet()
                db.session.add(selected_keyset)
                db.session.commit()
                print(f"Created new key set: {selected_keyset.id}")
            elif new_or_old == "2":
                print("Which keyset would you like to use?")
                for keyset in all_keysets:
                    # TODO: improve keyset details with related registration info
                    print(f"  {keyset.id} - {len(keyset.keys)} keys")

                keyset_id = input("Key Set ID: ")

                selected_keyset = KeySet.query.filter_by(id=keyset_id).first()
                if selected_keyset:
                    print(f"Using key set: {selected_keyset.id}")
                else:
                    print(
                        f"Unable to find keyset with key set ID '{keyset_id}'. Cancelling..."
                    )
                    return None

            else:
                print(f"Invalid option '{new_or_old}'. Cancelling...")
                return None

            return selected_keyset

        def create_keys(keyset, alg="RS256"):
            print("Starting key generation...")

            key = RSA.generate(4096)

            print("Generating Private Key...")
            private_key = key.exportKey()

            print("Generating Public Key...")
            public_key = key.publickey().exportKey()

            newkey = Key(
                key_set_id=keyset.id,
                public_key=public_key,
                private_key=private_key,
                alg=alg,
            )
            db.session.add(newkey)
            db.session.commit()
            print(
                f"Created new Public and Private key #{newkey.id} ({newkey.alg}) "
                f"in key set #{newkey.key_set_id}"
            )

        keyset = get_keyset()
        if not keyset:
            print("Unable to get valid keyset. Exiting.")
            return 1

        create_keys(keyset)

        print(
            "Keys created.\n\n"
            "To add a new registration: \n"
            "- If you are using a makefile, run `make register`\n"
            "- If you are running this script directly, run `flask register`\n"
        )

    @app.cli.command("register")
    def add_registration():
        from models import KeySet, Registration, db

        platform_options = [
            {
                "name": "Production Canvas",
                "url_base": "https://sso.canvaslms.com",
                "issuer": "https://canvas.instructure.com",
            },
            {
                "name": "Test Canvas",
                "url_base": "https://sso.test.canvaslms.com",
                "issuer": "https://canvas.test.instructure.com",
            },
            {
                "name": "Beta Canvas",
                "url_base": "https://sso.beta.canvaslms.com",
                "issuer": "https://canvas.beta.instructure.com",
            },
            {
                "name": "Other Canvas Platform",
                "url_base": "replaceme",
                "issuer": "https://canvas.instructure.com",
            },
        ]

        print("Which platform are you using?")
        for index, platform in enumerate(platform_options, start=1):
            print(f"  {index} - {platform['name']}")

        platform_choice = input("Platform Number: ")

        try:
            platform_choice = int(platform_choice)
            assert platform_choice > 0

            selected_platform = platform_options[platform_choice - 1]
            if platform_choice == len(platform_options):
                # Update other platform url base from user input
                print("Provide your server url. Remove any trailing slashes.")
                platform_url = input("Server URL: ")
                selected_platform["url_base"] = platform_url

        except (AssertionError, IndexError, ValueError):
            print(f"Invalid option '{platform_choice}'")
            return

        print(f"Registering in {selected_platform['name']}...")

        # client_id
        print(f"Input the Client ID provided by {selected_platform['name']}s")
        client_id = input("Client ID: ")

        # key_set_id
        print("Which keyset would you like to use?")
        for keyset in KeySet.query.all():
            # TODO: improve keyset details with related registration info
            print(f"  {keyset.id} - {len(keyset.keys)} keys")

        keyset_id = input("Key Set ID: ")

        selected_keyset = KeySet.query.filter_by(id=keyset_id).first()
        if selected_keyset:
            print(f"Using key set: {selected_keyset.id}")
        else:
            print(f"Unable to find keyset with key set ID '{keyset_id}'. Cancelling...")
            # TODO: handle bad keyset case

        try:
            new_reg = Registration(
                issuer=selected_platform["issuer"],
                client_id=client_id,
                platform_login_auth_endpoint=(
                    f"{selected_platform['url_base']}/api/lti/authorize_redirect"
                ),
                platform_service_auth_endpoint=(
                    f"{selected_platform['url_base']}/login/oauth2/token"
                ),
                platform_jwks_endpoint=f"{selected_platform['url_base']}/api/lti/security/jwks",
                key_set_id=selected_keyset.id,
            )
            db.session.add(new_reg)
            db.session.commit()

            print(
                f"Created new registration: {new_reg.id}\n"
                "Don't forget to enable the Client ID!\n\n"
                "To add a deployment: \n"
                "- If you are using a makefile, run `make deploy`\n"
                "- If you are running this script directly, run `flask deploy`\n"
            )
        except IntegrityError:
            print("A registration with that issuer and client_id already exists.")
            # TODO: handle duplicate registration case

    @app.cli.command("deploy")
    def add_deployment():
        from models import Deployment, Registration, db

        print("Which registration would you like to add a deployment for?")
        for registration in Registration.query.all():
            print(
                f"  {registration.id} - {registration.client_id} {registration.issuer}\n"
                f"      ({len(registration.deployments)} deployments)"
            )
        reg_id = input("Select Registration: ")

        registration = Registration.query.filter_by(id=reg_id).first()
        if not registration:
            print(f"Unable to find registration with ID '{reg_id}'. Cancelling...")
            return

        print(
            f"Provide the new deployment ID to attach to registration {registration.id}"
        )
        deploy_id = input("Deployment ID: ")

        new_deploy = Deployment(
            deployment_id=deploy_id, registration_id=registration.id
        )
        db.session.add(new_deploy)
        db.session.commit()
        print(f"Added deployment {new_deploy.id} ({new_deploy.deployment_id}).")
