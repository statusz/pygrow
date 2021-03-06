"""Collections contain content documents and blueprints."""

from grow.common import utils
from grow.pods.collectionz import documents
from grow.pods.collectionz import messages
import json
import operator
import os

_all = '__no-locale'


class Error(Exception):
  pass


class CollectionNotEmptyError(Error):
  pass


class BadCollectionNameError(Error, ValueError):
  pass


class CollectionDoesNotExistError(Error, ValueError):
  pass


class CollectionExistsError(Error):
  pass


class BadFieldsError(Error, ValueError):
  pass


class NoLocalesError(Error):
  pass


class Collection(object):

  def __init__(self, pod_path, _pod):
    utils.validate_name(pod_path)
    self.pod = _pod
    self.collection_path = pod_path.lstrip('/content')
    self.pod_path = pod_path
    self._blueprint_path = os.path.join(self.pod_path, '_blueprint.yaml')

  def __repr__(self):
    return '<Collection "{}">'.format(self.collection_path)

  @classmethod
  def list(cls, pod):
    paths = pod.list_dir('/content/')
    # TODO: replace with depth
    clean_paths = set()
    for path in paths:
      parts = path.split('/')
      if len(parts) >= 2:  # Disallow files in root-level /content/ dir.
        clean_paths.add(os.path.join('/content', parts[0]))
    return [cls(pod_path, _pod=pod) for pod_path in clean_paths]

  def exists(self):
    return self.pod.file_exists(self._blueprint_path)

  def create_from_message(self, message):
    if self.exists():
      raise CollectionExistsError('{} already exists.'.format(self))
    self.update_from_message(message)
    return self

  @classmethod
  def get(cls, collection_path, _pod):
    collection = cls(collection_path, _pod)
    if not collection.exists():
      raise CollectionDoesNotExistError('{} does not exist.'.format(collection))
    return collection

  def get_doc(self, doc_path, locale=None):
    pod_path = os.path.join(self.pod_path, doc_path.lstrip('/'))
    doc = documents.Document(pod_path, locale=locale, _pod=self.pod, _collection=self)
    if not doc.exists():
      raise documents.DocumentDoesNotExistError('{} does not exist.'.format(doc))
    return doc

  @property
  @utils.memoize
  def yaml(self):
    return utils.parse_yaml(self.pod.read_file(self._blueprint_path))[0]

  def list_categories(self):
    return self.yaml.get('categories')

  @property
  def title(self):
    return self.yaml.get('title')

  def delete(self):
    if len(self.list_documents(include_hidden=True)):
      text = 'Collections that are not empty cannot be deleted.'
      raise CollectionNotEmptyError(text)
    self.pod.delete_file(self._blueprint_path)

  def update_from_message(self, message):
    if not message.fields:
      raise BadFieldsError('Fields are required to create a collection.')
    fields = json.loads(message.fields)
    fields = utils.dump_yaml(fields)
    self.pod.write_file(self._blueprint_path, fields)

  def get_view(self):
    return self.yaml.get('view')

  def get_path_format(self):
    return self.yaml.get('path')

  def list_documents(self, order_by=None, reverse=None, include_hidden=False, locale=_all):
    # TODO(jeremydw): Rename method to "search".
    if order_by is None:
      order_by = 'order'
    if reverse is None:
      reverse = False

    paths = self.pod.list_dir(self.pod_path)
    sorted_docs = utils.SortedCollection(key=operator.attrgetter(order_by))
    for path in paths:
      doc_path = path.replace('/content/', '')
      slug, ext = os.path.splitext(os.path.basename(doc_path))
      if (slug.startswith('_')
          or ext not in messages.extensions_to_formats
          or not doc_path):
        continue
      doc = self.get_doc(doc_path)
      if not include_hidden and doc.is_hidden:
        continue

      if locale in [_all, None]:
        sorted_docs.insert(doc)

      if locale is None:
        continue

      for each_locale in doc.list_locales():
        if each_locale == locale or locale == _all:
          doc = self.get_doc(doc_path, locale=each_locale)
          if not include_hidden and doc.is_hidden:
            continue
          sorted_docs.insert(doc)

    return reversed(sorted_docs) if reverse else sorted_docs

  def list_servable_documents(self, include_hidden=False):
    docs = []
    for doc in self.list_documents(include_hidden=include_hidden):
      if self.yaml.get('draft'):
        continue
      if not doc.has_url() or not doc.get_view():
        continue
      docs.append(doc)
    return docs

  @property
  def localization(self):
    return self.yaml['localization']

  def list_locales(self):
    if 'localization' in self.yaml:
      try:
        return self.localization['locales']
      except KeyError:
        raise NoLocalesError('{} has no locales.')
    return []

  def search_documents(self, order_by='order'):
    return self.list_documents(order_by=order_by)

  def to_message(self):
    message = messages.CollectionMessage()
    message.title = self.title
    message.collection_path = self.collection_path
    return message
