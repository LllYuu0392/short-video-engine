from setuptools import setup, find_packages

setup(
    name='mimo-content-pipeline',
    version='1.0.0',
    description='基于小米MiMo的多Agent自媒体内容工厂',
    author='LllYuu0392',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'openai>=1.0.0',
        'requests>=2.28.0',
    ],
    python_requires='>=3.8',
)
