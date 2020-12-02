PY_FILES = $(shell find thunder/ -type f -name '*.py')

install: uninstall build
	pip install --user dist/thunder-*.tar.gz

build: $(PY_FILES)
	python setup.py sdist bdist_wheel

uninstall:
	pip uninstall -y thunder

clean:
	rm -rf build/ dist/ thunder.egg-info/
