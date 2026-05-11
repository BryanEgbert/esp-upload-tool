CERT_FILE ?= certificate.pem
KEY_FILE ?= private.key
CERT_PASSWORD ?= XmjZk7Yq9Qmzo68ulRLL
TIMESTAMP_URL ?= http://timestamp.digicert.com
APP_URL ?= https://github.com/BryanEgbert/esp-upload-tool
ESPTOOL_PATH=env/lib/python3.13/site-packages/esptool

sign-exe:
	@echo "Signing executable with osslsigncode..."
	@mkdir -p build
	@{ \
		if [ -n "$(FILE)" ]; then \
			EXECUTABLE_TO_SIGN="$(FILE)"; \
		else \
			EXECUTABLE_TO_SIGN="$(EXECUTABLE)"; \
		fi; \
		if [ -z "$$EXECUTABLE_TO_SIGN" ] || [ "$$EXECUTABLE_TO_SIGN" = "none" ]; then \
			echo "Error: No executable found."; exit 1; \
		fi; \
		if [ ! -f "$$EXECUTABLE_TO_SIGN" ]; then \
			echo "Error: File $$EXECUTABLE_TO_SIGN not found."; exit 1; \
		fi; \
		FILE_BASE=$$(basename "$$EXECUTABLE_TO_SIGN" .exe); \
		SIGNED_OUTPUT="$$FILE_BASE-signed.exe"; \
		if [ ! -f "$(CERT_FILE)" ] || [ ! -f "$(KEY_FILE)" ]; then \
			echo "Certificate not found, creating self-signed cert..."; \
			openssl req -x509 -newkey rsa:4096 -keyout "$(KEY_FILE)" -out "$(CERT_FILE)" -days 365 -nodes \
				-subj "/C=US/ST=State/L=City/O=ESPUploadTOol/OU=Development/CN=ESPUploadTOol"; \
		fi; \
		echo "Signing $$EXECUTABLE_TO_SIGN -> $$SIGNED_OUTPUT"; \
		osslsigncode sign \
			-certs "$(CERT_FILE)" \
			-key "$(KEY_FILE)" \
			-n "$(APP_NAME)" \
			-i "$(APP_URL)" \
			-t "$(TIMESTAMP_URL)" \
			-in "$$EXECUTABLE_TO_SIGN" \
			-out "$$SIGNED_OUTPUT"; \
		echo "Done: $$SIGNED_OUTPUT (self-signed, verification skipped)"; \
	}

nuitka-build:
	python -m nuitka --standalone --onefile \
		--enable-plugin=pyside6 \
		--include-package=esptool \
		--include-package=PySide6.QtOpenGL \
		--include-data-dir=$(ESPTOOL_PATH)/targets/stub_flasher=esptool \
		main.py