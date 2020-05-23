#!/usr/bin/env python
import hashlib
import json
import os
import re
import sys

from io import BytesIO
from ricecooker.utils import downloader, html_writer
from ricecooker.chefs import SushiChef
from ricecooker.classes import nodes, files, questions, licenses
from ricecooker.config import LOGGER              # Use LOGGER to print messages
from ricecooker.exceptions import raise_for_invalid_channel
from le_utils.constants import exercises, content_kinds, file_formats, format_presets, languages

from bs4 import BeautifulSoup
from PIL import Image

# Run constants
################################################################################
CHANNEL_NAME = "Stanford Digital Medic"                     # Name of Kolibri channel
CHANNEL_SOURCE_ID = "sushi-chef-stanford-digital-medic"     # Unique ID for content source
CHANNEL_DOMAIN = "digitalmedic.stanford.edu"                # Who is providing the content
CHANNEL_LANGUAGE = "en"                                     # Language of channel
CHANNEL_DESCRIPTION = "From the Stanford Center for " \
    "Health Education, these infographics and visual " \
    "materials provide key information on high-priority " \
    "topics related to the prevention and understanding of COVID-19."
CHANNEL_THUMBNAIL = "https://4ao7ry48spy847yi1v2f88gj-wpengine.netdna-ssl.com/wp-content/uploads/2019/06/logo_horizontal-A_white.png"

# Additional constants
################################################################################
# Folder to store pdfs of images
DOCUMENT_DOWNLOAD_DIR = 'documents'
if not os.path.exists(DOCUMENT_DOWNLOAD_DIR):
    os.makedirs(DOCUMENT_DOWNLOAD_DIR)

# Main page collection brandfolder
ENGLISH_COLLECTION_URL = "https://brandfolder.com/digitalmedic/covid-19"
ENGLISH_ASSETS_URL = "https://brandfolder.com/api/v4/collections/{collection}/sections/{section}/assets?sort_by=position&order=ASC&search=&fast_jsonapi=true"
EXCLUDED_TOPIC_IDS = [262354, 261412]
FILE_STORAGE_URL = "https://brandfolder.com/api/v4/assets/{id}/attachments?fields=url,thumbnail_url"

# Multi-language content constants
SLIDESHOWS_URL = "https://brandfolder.com/digitalmedic/covid-19-multiple-languages"
SLIDESHOW_ASSETS_URL = "https://brandfolder.com/api/v4/collections/{collection}/sections/{section}/assets?sort_by=position&order=ASC&strict_search=false&fast_jsonapi=true"
LICENSE = licenses.CC_BY_SALicense(copyright_holder="Stanford Center for Health Education")

LANGUAGE_MAP = {
    'Afrikaans': 'af',
    'Arabic': 'ar',
    'English': 'en',
    'French': 'fr',
    'Hindi': 'hi',
    'isiXhosa': 'xh',
    'isiZulu': 'zul',
    'Kiswahili': 'sw',
    'Mandarin Chinese - simple': 'zh-CN',
    'Mandarin Chinese - Traditional': 'zh-Hant',
    'Portuguese': 'pt',
    'Setswana': 'tn',
    'Spanish': 'es',
    'Tetun': None,
}

# The chef subclass
################################################################################
class StanfordDigitalMedicChef(SushiChef):
    """
    This class converts content from the content source into the format required by Kolibri,
    then uploads the {channel_name} channel to Kolibri Studio.
    Your command line script should call the `main` method as the entry point,
    which performs the following steps:
      - Parse command line arguments and options (run `./sushichef.py -h` for details)
      - Call the `SushiChef.run` method which in turn calls `pre_run` (optional)
        and then the ricecooker function `uploadchannel` which in turn calls this
        class' `get_channel` method to get channel info, then `construct_channel`
        to build the contentnode tree.
    For more info, see https://ricecooker.readthedocs.io
    """
    channel_info = {
        'CHANNEL_SOURCE_DOMAIN': CHANNEL_DOMAIN,
        'CHANNEL_SOURCE_ID': CHANNEL_SOURCE_ID,
        'CHANNEL_TITLE': CHANNEL_NAME,
        'CHANNEL_LANGUAGE': CHANNEL_LANGUAGE,
        'CHANNEL_THUMBNAIL': CHANNEL_THUMBNAIL,
        'CHANNEL_DESCRIPTION': CHANNEL_DESCRIPTION,
    }
    # Your chef subclass can override/extend the following method:
    # get_channel: to create ChannelNode manually instead of using channel_info
    # pre_run: to perform preliminary tasks, e.g., crawling and scraping website
    # __init__: if need to customize functionality or add command line arguments

    def construct_channel(self, *args, **kwargs):
        """
        Creates ChannelNode and build topic tree
        Args:
          - args: arguments passed in on the command line
          - kwargs: extra options passed in as key="value" pairs on the command line
            For example, add the command line option   lang="fr"  and the value
            "fr" will be passed along to `construct_channel` as kwargs['lang'].
        Returns: ChannelNode
        """
        channel = self.get_channel(*args, **kwargs)  # Create ChannelNode from data in self.channel_info

        scrape_english_collection(channel)
        scrape_multilanguage_slideshows(channel)

        return channel

# HELPER FUNCTIONS
################################################################################
def get_collection_key(contents):
    return re.search(r"var SOURCE\s*=\s*\{.+, resource_key: \"(.+)\"[^\}]+", contents.text).group(1)


def create_slideshow(images, source_id, title, language_name):
    """
        images: {url: str, caption: str}
    """

    thumbnailFile = files.ThumbnailFile(images[0]['url'])

    if '--slides' in sys.argv:
        slides = [
            files.SlideImageFile(image['url'], caption=image.get('caption', ''))
            for image in images
        ]
        return nodes.SlideshowNode(
            source_id=source_id,
            title=title,
            license=LICENSE,
            language=LANGUAGE_MAP[language_name],
            files=[thumbnailFile] + slides
        )

    # Create PDF
    filename = hashlib.md5(source_id.encode('utf-8')).hexdigest()
    pdfpath = '{}{}{}.pdf'.format(DOCUMENT_DOWNLOAD_DIR, os.path.sep, filename)

    if not os.path.exists(pdfpath):
        image_list = []
        for image in images:
            img = Image.open(BytesIO(downloader.read(image['url'])))
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            image_list.append(img)

        image_list[0].save(pdfpath, save_all=True, append_images=image_list[1:])

    return nodes.DocumentNode(
        source_id=source_id,
        title=title,
        license=LICENSE,
        language=LANGUAGE_MAP[language_name],
        files=[thumbnailFile, files.DocumentFile(pdfpath)]
    )



# SCRAPING FUNCTIONS
################################################################################
def scrape_english_collection(channel):
    LOGGER.info('Scraping English collection...')
    contents = BeautifulSoup(downloader.read(ENGLISH_COLLECTION_URL), 'html5lib')
    collection_key = get_collection_key(contents)

    topic_selection = contents.find('div', {'class': 'asset-list'}).find('div')
    topic_list = [t for t in json.loads(topic_selection['data-react-props'])['sections'] if t['id'] not in EXCLUDED_TOPIC_IDS]

    # TODO: descriptions

    for topic in topic_list:
        LOGGER.info('    {}'.format(topic['name'].encode('utf-8')))
        topic_node = nodes.TopicNode(source_id=topic['section_key'], title=topic['name'])
        channel.add_child(topic_node)

        # Scrape items in the topic
        url = ENGLISH_ASSETS_URL.format(collection=collection_key, section=topic['section_key'])
        scrape_collection_files(topic_node, url)


def scrape_collection_files(topic, url):
    assets = json.loads(downloader.read(url))['data']
    images = []
    for asset in assets:
        if asset['attributes']['extension'] == 'png':
            images.append({
                'url': asset['attributes']['thumbnail_url'].replace('element.png', 'view@2x.png'),
                'caption': asset['attributes']['name']
            })

        elif asset['attributes']['extension'] == 'mp4':
            video_data = json.loads(downloader.read(FILE_STORAGE_URL.format(id=asset['id'])))
            video = video_data['data'][0]['attributes']
            topic.add_child(nodes.VideoNode(
                source_id=video['url'],
                title=asset['attributes']['name'],
                license=LICENSE,
                files=[
                    files.VideoFile(video['url']),
                    files.ThumbnailFile(video['thumbnail_url'])
                ]
            ))
        else:
            LOGGER.warning('Unable to add {} from {}'.format(asset['attributes']['extension'], url))

    # Add images to slideshow node
    if len(images):
        topic.add_child(create_slideshow(
            images,
            url,
            topic.title,
            'English'
        ))


def scrape_multilanguage_slideshows(channel):
    LOGGER.info('Scraping multi-language content...')
    contents = BeautifulSoup(downloader.read(SLIDESHOWS_URL), 'html5lib')
    collection_key = get_collection_key(contents)

    languages_selection = contents.find('div', {'class': 'asset-list'}).find('div')
    language_list = json.loads(languages_selection['data-react-props'])['sections']

    for language in language_list:
        asset_url = SLIDESHOW_ASSETS_URL.format(collection='qac6i4-foozd4-68u325', section=language['section_key'])
        slide_data = json.loads(downloader.read(asset_url))['data']
        translated_name = languages.getlang(LANGUAGE_MAP[language['name']]).native_name if LANGUAGE_MAP[language['name']] else language['name']
        LOGGER.info('    {}'.format(translated_name.encode('utf-8')))

        slides = [
            { 'url': slide['attributes']['thumbnail_url'].replace('element.png', 'view@2x.png')}
            for slide in slide_data
        ]
        if len(slides):
            channel.add_child(create_slideshow(
                slides,
                asset_url,
                translated_name,
                language['name']
            ))


# CLI
################################################################################
if __name__ == '__main__':
    # This code runs when sushichef.py is called from the command line

    # Use `-- --slides` to use slideshows instead of pdfs
    chef = StanfordDigitalMedicChef()
    chef.main()