from setuptools import setup, find_namespace_packages

package_data = {
	'': ['*.json', 'py.typed'],
	'conf': [
		'ampel-core/*.yaml', 'ampel-core/*.yml', 'ampel-core/*.json',
		'ampel-core/**/*.yaml', 'ampel-core/**/*.yml', 'ampel-core/**/*.json',
	],
	'ampel.test': ['test-data/*.json'],
}

entry_points = {
	'cli': [
		'ajob Run argo enhanced schema file(s) = ampel.cli.ArgoJobCommand',
	]
}

setup(
    name = 'ampel-argo-job',
    version = '0.9.0',
    description = 'Ampel jobs with Argo workflows',
    author = 'Jakob van Santen',
    maintainer = 'Jakob van Santen',
    maintainer_email = 'jakob.van.santen@desy.de',
    url = 'https://ampelproject.github.io',
    zip_safe = False,
    packages = find_namespace_packages(),
    package_data = package_data,
    entry_points = entry_points,
    python_requires = '>=3.10,<4.0'
)
