from setuptools import setup, find_packages

setup(
    name='flex',
    version='1.0.2',
    description='Framework for Laboratory EXperiments',
    author='Pubudu Wijesinghe',
    author_email='pubudu.wijesinghe@levylab.org',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},  
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.11',
    install_requires=[
        'matplotlib', 
        'numpy',
        'psycopg2', 
        'pyzmq', 
        'pyvisa', 
        'tqdm', 
        'pandas', 
        'asana', 
        'requests', 
        'nidaqmx',
        'pythonnet',
        'pyserial',
        'pywin32'
    ],
)
