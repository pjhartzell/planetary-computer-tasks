# Creating a dataset

This guide will walk through creating a new dataset for processing in PCTasks, using an existing dataset as an example, which can be found in the
[datasets/chesapeake_lulc](https://github.com/microsoft/planetary-computer-tasks/tree/main/datasets/chesapeake_lulc) folder.

## dataset.yaml

In the `datasets/chesapeake_lulc` folder, you'll see a file called `dataset.yaml`. This is the YAML configuration that
will tell PCTasks all it needs to know to create workflows for ingesting this dataset. It includes information about
the STAC Collections for this dataset, where the assets are, what tokens it needs, what code files are needed to
processes the dataset, etc. It also includes sections that are the same as a PCTasks workflow and task configuration, such as `image`, `code`,
and `environment`. These sections are forwarded directly into the workflows that are generated by running `pctasks dataset` commands
against the dataset configuration file.

The file in full is here; we will walk through the sections below:

```yaml
name: chesapeake_lulc
image: ${{ args.registry }}/pctasks-task-base:latest

args:
- registry

code:
  src: ${{ local.path(./chesapeake_lulc.py) }}
  requirements: ${{ local.path(./requirements.txt) }}

environment:
  AZURE_TENANT_ID: ${{ secrets.task-tenant-id }}
  AZURE_CLIENT_ID: ${{ secrets.task-client-id }}
  AZURE_CLIENT_SECRET: ${{ secrets.task-client-secret }}

collections:
  - id: chesapeake-lc-7
    template: ${{ local.path(./collection/chesapeake-lc-7) }}
    class: chesapeake_lulc:ChesapeakeCollection
    asset_storage:
      - uri: blob://landcoverdata/chesapeake
        token: ${{ pc.get_token(landcoverdata, chesapeake) }}
        chunks:
          options:
            name_starts_with: lc-7/
            chunk_length: 1000
    chunk_storage:
      uri: blob://landcoverdata/chesapeake-etl-data/pctasks-chunks/lc-7/
  - id: chesapeake-lc-13
    template: ${{ local.path(./collection/chesapeake-lc-13) }}
    class: chesapeake_lulc:ChesapeakeCollection
    asset_storage:
      - uri: blob://landcoverdata/chesapeake
        token: ${{ pc.get_token(landcoverdata, chesapeake) }}
        chunks:
          options:
            name_starts_with: lc-13/
            chunk_length: 1000
    chunk_storage:
      uri: blob://landcoverdata/chesapeake-etl-data/pctasks-chunks/lc-13/
  - id: chesapeake-lu
    template: ${{ local.path(./collection/chesapeake-lu) }}
    class: chesapeake_lulc:ChesapeakeCollection
    asset_storage:
      - uri: blob://landcoverdata/chesapeake
        token: ${{ pc.get_token(landcoverdata, chesapeake) }}
        chunks:
          options:
            name_starts_with: lu/
            chunk_length: 1000
    chunk_storage:
      uri: blob://landcoverdata/chesapeake-etl-data/pctasks-chunks/lu/

```

### Templating

You'll notice the usage of `${{ ... }}` in the dataset YAML for various values. This represents a templated value that is dynamically
computed by PCTasks, either on the client or server side. See the [](../user_guide/templating) user guide for more information about templating.

### name

```yaml
name: chesapeake_lulc
```

This section simply gives the dataset a name. Use an ID that can be put into file paths etc (no spaces).

### image and args

```yaml
image: ${{ args.registry }}/pctasks-task-base:latest

args:
- registry
```

This section describes the docker image to use to run tasks. The main requirement is that `pctasks.dataset` and `pctasks.ingest_task` are
installed in the environment of the docker image. Otherwise you can use any image to run the task. It's recommended to use
`pctasks-task-base` when possible, or an image derived from that base image.

### code

```yaml
code:
  src: ${{ local.path(./chesapeake_lulc.py) }}
  requirements: ${{ local.path(./requirements.txt) }}
```

The code section allows you to specify a local code file or package that should be uploaded and available to the task runner when executing
tasks. You can also supply a local `requirements.txt` file that lists dependencies that should be installed before running tasks. If installing
dependencies will take a significant amount of time, it is recommended that you instead create and publish a docker image with those dependencies
installed and use that image to speed things up. See [](../user_guide/runtime) for more details.

### environment

```yaml
environment:
  AZURE_TENANT_ID: ${{ secrets.task-tenant-id }}
  AZURE_CLIENT_ID: ${{ secrets.task-client-id }}
  AZURE_CLIENT_SECRET: ${{ secrets.task-client-secret }}
```

The `environment` provides the ability to inject environment variables into each task that is issued for the dataset. In this case, we're injecting the Azure SDK credentials for tasks. These environment variables will be provided to each task, regardless
of whether they will be utilized in any specific task. In this case, the variable values are using the `${{ secrets.* }}` template
group to retrieve secret values. See [](../user_guide/secrets) for more details about secrets.

### collections

The `collections` element is a list of collection configuration. If your dataset only has one collection,
there will be a single object listed here. We'll look at the first collection object as an example; the
rest are similar:

```yaml
  - id: chesapeake-lc-7
    template: ${{ local.path(./collection/chesapeake-lc-7) }}
    class: chesapeake_lulc:ChesapeakeCollection
    asset_storage:
      - uri: blob://landcoverdata/chesapeake
        token: ${{ pc.get_token(landcoverdata, chesapeake) }}
        chunks:
          options:
            name_starts_with: lc-7/
            chunk_length: 1000
    chunk_storage:
      uri: blob://landcoverdata/chesapeake-etl-data/pctasks-chunks/lc-7/
```

#### id

```yaml
id: chesapeake-lc-7
```

This is the STAC Collection ID. For any STAC Items that are processed, this will either be set into their `collection`
property if none is set, or throw an error if the Item's `collection` does not match this value. This must also
match the ID in the collection template.

#### template

```yaml
template: ${{ local.path(./collection/chesapeake-lc-7) }}
```

This is the path to the directory containing the Collection template. The collection template is

Note here we use the PCTasks template function `local.path` to specify the path to the template directory relative to the location of the `dataset.yaml` path.

#### class

```yaml
class: chesapeake_lulc:ChesapeakeCollection
```

The class property points PCTasks to the `pctasks.dataset.collection.Collection` subclass that will be used to process STAC Items.
This must be a class accessible in the Python path of the task execution environment, either through the code or packages described
in the `code` configuration block described above, packages installed in the docker image, or core PCTasks implementations such as `pctasks.dataset.collection:PremadeItemCollection`.

The implementation of the class is described below.

#### asset_storage

There can be multiple asset storage configurations, which describes where assets for the dataset exist, are specified in the list elements of `asset_storage` property. We'll look at the single asset_storage configuration here:

```yaml
uri: blob://landcoverdata/chesapeake
token: ${{ pc.get_token(landcoverdata, chesapeake) }}
chunks:
    options:
        name_starts_with: lc-7/
        chunk_length: 1000
```

 The `uri` is the PC URI to the assets (currently must be a `blob://storage_account/container(/prefix)` type URI).

 The `token` provides a SAS token to access the assets. Any token provided with asset storage will be available to tasks through the {ref}`StorageFactory` mechanism.

The `chunks` section describes how the dataset assets get translated into "chunk files". Chunk files are simple lists of asset URIs
that are used to break data processing work into groups of work that can be processed in parallel. This section would also
contain information defining the "splits" that would parallelize the creation of chunk files, though this particular dataset
does not utilize splits and so no options are defined. See [](../user_guide/chunking) for more information about splits and chunk files.

#### chunk_storage

```yaml
chunk_storage:
    uri: blob://landcoverdata/chesapeake-etl-data/pctasks-chunks/lc-7/
```

This section defines where chunk files will be stored. You can supply a read/write SAS token in this configuration, but in this example we only specify the URI, which requires the service principal whose credentials are set in the `environment` have read/write access to this container. See [](../user_guide/chunking) for more information about chunk files.

## Collection templates

A Collection template is a directory has two files: `template.json`, which
is a STAC Collection JSON with a templated description value, and a `description.md`, which contains the text that will be
templated into the Collection JSON.

For example, using

```shell
> pctasks dataset ingest-collection -d datasets/chesapeake_lulc/dataset.yaml -c chesapeake-lc-7 --submit
```

will submit a task to write the collection to the database. Note that if your dataset only has a single collection, you
do not have to supply the `-c` option. Also, if you are in the dataset directory and your dataset is named `dataset.yaml`,
you do not have to supply teh `-d` option.

## chesapeake_lulc.py

This is the code file that contains the subclass of [pctasks.dataset.model.collection.Collection](../reference/generated/pctasks.dataset.collection.Collection). This dataset uses a [stactools package](https://stactools-packages.github.io/) for Item
creation, so the code quite simply calls out to that stactools package to create an item from an asset:

```python
from typing import List, Union

import pystac
from stactools.chesapeake_lulc.stac import create_item

from pctasks.core.models.task import WaitTaskResult
from pctasks.core.storage import StorageFactory
from pctasks.dataset.collection import Collection


class ChesapeakeCollection(Collection):
    @classmethod
    def create_item(
        cls, asset_uri: str, storage_factory: StorageFactory
    ) -> Union[List[pystac.Item], WaitTaskResult]:
        storage, asset_path = storage_factory.get_storage_for_file(asset_uri)
        href = storage.get_url(asset_path)
        item = create_item(href, read_href_modifier=storage.sign)
        return [item]
```

See the [chesapeake-lulc stactools package](https://github.com/stactools-packages/chesapeake-lulc) for an example
of how to create a stactools package. It's recommended that any public dataset ingestion starts with a stactools package,
which allows community involvement in the generation of STAC for public datasets.


## requirements.txt

This file contains the requirements that are needed to run the code contained in `chesapeake_lulc.py` file. Since this
is declared in the `code:` block of the `dataset.yaml` file, this requirements file along with the code file will be
uploaded and then transferred to task runners, which will install the dependencies before running any task.

Because installation of dependencies can be time consuming, you can speed up the running of dataset tasks by
creating and publishing a docker image that already contains the requirements and code. The image must be available
to be `docker pull`'d by the task runner. In that scenario, you would not need to supply a `code:` block in the
dataset configuration.

## Running the dataset

With the above configuration file, code files, and collection templates, you can ingest the dataset into the development or deployed PCTasks system.

With the appropriate profile set, use:

```shell
> pctasks dataset ingest-collection -d dataset.yaml -c chesapeake-lc-7 --submit
> pctasks dataset process-items -d dataset.yaml -c chesapeake-lc-7 test-ingest --limit 1 --submit
```

The above `process-items` command will limit the number of Items processed for testing.
Also note that, because our dataset has multiple collections, you need to pass in the
`-c` argument with the collection name. If your dataset only has a single argument, this
option is not required. The `--submit` option will submit the generated workflow to PCTasks;
if not supplied, then the workflow will be printed to stdout, which can be submitted later through
the `pctasks submit workflow` command.