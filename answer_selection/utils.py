import unicodedata
from torch import LongTensor, FloatTensor, ByteTensor
import numpy as np
from nltk.tokenize import word_tokenize
from collections import defaultdict
import re


class Dictionary:
    def __init__(self):
        dct = dict()
        # NULL for padding, UNK for unknown word
        dct['<NULL>'] = 0
        dct['<UNK>'] = 1
        self.dct = dct

    def __len__(self):
        return len(self.dct)

    def __contains__(self, item):
        item = Dictionary.normalize(item)
        return item in self.dct

    def __setitem__(self, key, value):
        key = Dictionary.normalize(key)
        self.dct[key] = value

    def __getitem__(self, item):
        item = Dictionary.normalize(item)
        return self.dct.get(item, 1)

    def add(self, key):
        key = Dictionary.normalize(key)
        if key not in self.dct:
            self.dct[key] = len(self.dct)

    @staticmethod
    def normalize(w):
        return unicodedata.normalize('NFD', w)


class Sample:
    def __init__(self, input_dict, word_dict):
        self.q_id = input_dict['q_id']
        self.q_text = ' '.join(input_dict['q'])
        self.a_text = [' '.join(answer) for ans_lst in input_dict['a'] for answer in ans_lst]
        self.t_text = ' '.join(input_dict['t'])
        self.snippet_text = ' '.join(input_dict['snippet'])

        self.span = LongTensor(input_dict['span'])
        self.q_words = LongTensor([word_dict[w] for w in input_dict['q']])
        self.d_words = LongTensor([word_dict[w] for w in input_dict['snippet']])


def get_qa_pair(data, q_types=['factoid']):
    """
    :param data: data having the same format as BioASQ data
    :param q_types: desired question types
    :return: qa_pair having the question, answer list, question type, snippet
    """

    # Unify answer format and separate punctuations by spaces.
    def unify_answer_format(obj, a):
        if obj['type'] == 'factoid' and not isinstance(a[0], list):
            a = [a]
        unified_a = []
        for answer_lst in a:
            unified_answer_lst = [separate_punctuation_by_space(synonym) for synonym in answer_lst]
            unified_a.append(unified_answer_lst)
        return unified_a

    # Separate snippets, de-duplicate them and separate punctuations by spaces.
    def get_snippets(obj):
        dup_count = 0
        snippets = []
        for snippet in obj['snippets']:
            snippet = separate_punctuation_by_space(snippet['text'])
            if snippet not in snippets:
                snippets.append(snippet)
            else:
                dup_count += 1
        return snippets, dup_count

    qa_pair = []
    duplicate_snippet_count = 0
    for obj in data['questions']:
        if obj['type'] in q_types:
            q = separate_punctuation_by_space(obj['body'])
            a = unify_answer_format(obj, obj['exact_answer'])
            t = obj['type']
            s, count = get_snippets(obj)
            duplicate_snippet_count += count

            if len(s) > 0:
                qa_pair.append([q, a, t, s])
    print('duplicate snippet count:', duplicate_snippet_count)
    print('questions count:', len(qa_pair))
    return qa_pair


def separate_punctuation_by_space(text):
    return ' '.join(word_tokenize(text))


def get_spans(a, snippet):
    snippet = snippet.lower()
    spans = []
    for synonym_lst in a:
        for synonym in synonym_lst:
            synonym = synonym.lower()
            synonym = re.escape(synonym)

            # Get the start position in the text
            span = [(m.start(), m.end() - 1) for m in re.finditer(synonym, snippet)]

            # Convert them into positions in the word list
            span = [(len(snippet[:start].split(' ')) - 1, len(snippet[:end + 1].split(' ')) - 1) for (start, end) in
                    span]

            if len(span):
                spans += span
    return spans


def add_span(qa_pair):
    new_qa_pair = []
    for (q, a, t, s) in qa_pair:
        new_s, new_span_lst = [], []
        # one list of spans per snippet
        span_lst = [get_spans(a, snippet) for snippet in s]
        for (snippet, spans) in zip(s, span_lst):
            if len(spans):
                new_s.append(snippet)
                new_span_lst.append(spans)
        if len(new_span_lst):
            new_qa_pair.append([q, a, t, new_s, new_span_lst])
    print('{}/{}={} question have exact answer in span'.format(len(new_qa_pair), len(qa_pair),
                                                               len(new_qa_pair) / len(qa_pair)))
    return new_qa_pair


def text_to_list(qa_pair):
    result = []
    for (q, a, t, s, span_lst) in qa_pair:
        new_a = []
        for ans_lst in a:
            new_a.append([answer.split(' ') for answer in ans_lst])
        result.append([q.split(' '), new_a, t, [snippet.split(' ') for snippet in s], span_lst])
    return result


def bioclean(t):
    return ' '.join(re.sub('[.,?;*!%^&_+():-\[\]{}]', '',
                           (t.replace('"', '').replace('/', '')
                            .replace('\\', '').replace("'", '')
                            .strip().lower()))
                    .split())


def get_word_dict(qa_pair, clean_func, dct=None):
    dct = Dictionary() if dct is None else dct
    original_len = len(dct)
    for (q, a, t, s, span_lst) in qa_pair:
        for word in q:
            dct.add(clean_func(word))
        for ans_lst in a:
            for ans in ans_lst:
                for word in ans:
                    dct.add(clean_func(word))
        for snippet in s:
            for word in snippet:
                dct.add(clean_func(word))
    print('vocabulary from {} to {}'.format(original_len, len(dct)))
    return dct


# (q, a, t, s, span_lst)
def squad_to_bioasq_format(data):
    qa_pair = []
    for domain in data['data']:
        for paragraph in domain['paragraphs']:
            s = [separate_punctuation_by_space(paragraph['context'])]
            t = 'factoid'
            # format: [{answers, question}, ...]
            for qa in paragraph['qas']:
                q = separate_punctuation_by_space(qa['question'])
                a = []
                answers = qa['answers']
                for answer_dct in answers:
                    answer = separate_punctuation_by_space(answer_dct['text'])
                    if answer not in a:
                        a.append(answer)
                a = [a]
                qa_pair.append([q, a, t, s])
    print('questions count:', len(qa_pair))
    return qa_pair





q_id = 0


def flatten_span_list(qa_pair):
    global q_id;
    new_qa_pair = []
    for (q, a, t, s, span_lst) in qa_pair:
        for (snippet, spans) in zip(s, span_lst):
            for span in spans:
                new_qa_pair.append([q, a, t, snippet, span, q_id])
        q_id += 1
    return new_qa_pair


def formalize_data(qa_pair, word_dict):
    formal_data = []
    for (q, a, t, snippet, span, q_id) in qa_pair:
        formal_data.append(Sample({'q': q, 'a': a, 't': t, 'snippet': snippet, 'span': span, 'q_id': q_id}, word_dict))
    return formal_data

def evaluate(data):
    for sample in data:
        pass
