"""Correções confirmadas de identidade e exercício, sem alterar os registros originais."""
import re

from .music_events_import import norm

# Orientação administrativa: preservar o cadastro, excluir da relação de encarregados.
RETIRED = {norm(name) for name in (
    'GETÚLIO SANTIAGO COSTA', 'GETÚLIO SANTIAGO',
    'JOSÉ RICARDO BARDELI', 'JOSÉ RICARDO BARDELLI', 'RICARDO BARDELLI',
    'SILAS AGUIAR ROCHA', 'SILAS AGUIAR',
)}


def conductor_name(name, common_key=''):
    value = ' '.join(str(name or '').split())
    if common_key == 'BR-22-1804' and norm(value) == 'MICHEL FRANK BOMFIM CHAVES':
        return 'MICHEL FRANK BONFIM CHAVES'
    if common_key == 'BR-22-2590' and norm(value) == 'DIOGO CAMARGO':
        return 'DIOGO LUCAS DE CAMARGO'
    if norm(value) in {'OSEIA DE SOUZA', 'OSEIAS DE SOUZA'}:
        return 'OSÉIA DE SOUZA'
    if common_key == 'BR-22-3789' and norm(value) in {'ELCIO MONTEIRO DOS REIS', 'ELCIO MONTEIRO REIS'}:
        return 'ELCIO MONTEIRO REIS'
    return value


def active_conductor(name):
    return norm(name) not in RETIRED


def common_name_key(label):
    return norm(re.sub(r'^BR-\d+-\d+\s*-\s*', '', str(label or '')))
