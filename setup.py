from setuptools import setup, find_packages

setup(name='moda',
      version='0.0.1',
      description='Xyla\'s styling and user interaction library.',
      url='https://github.com/xyla-io/moda',
      author='Xyla',
      author_email='gklei89@gmail.com',
      license='MIT',
      packages=find_packages(),
      install_requires=[
        'pytest',
        'click',
        'Pygments',      
      ],
      zip_safe=False)