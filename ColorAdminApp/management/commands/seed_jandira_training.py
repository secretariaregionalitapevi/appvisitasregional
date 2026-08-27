import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError


MARKER = "TREINAMENTO JANDIRA 20260827"
POLOS = (
    "BR-22-0750 - PARQUE SANTA TEREZA - JANDIRA",
    "BR-22-3251 - JARDIM STELLA MARIS",
)


def headers(prefer="return=representation"):
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def url(table):
    return f"{settings.SUPABASE_URL}/rest/v1/{table}"


def children_for(polo, polo_number):
    first_names = (
        ("Ana Clara", "F", "2020-10-12"),
        ("Beatriz", "F", "2019-07-05"),
        ("Cecilia", "F", "2018-11-18"),
        ("Eloisa", "F", "2017-09-22"),
        ("Helena", "F", "2021-02-14"),
        ("Isabela", "F", "2020-04-09"),
        ("Laura", "F", "2019-12-03"),
        ("Manuela", "F", "2018-06-27"),
        ("Arthur", "M", "2021-01-19"),
        ("Davi", "M", "2020-08-30"),
        ("Gabriel", "M", "2019-03-11"),
        ("Heitor", "M", "2018-10-16"),
        ("Lucas", "M", "2017-12-08"),
        ("Miguel", "M", "2020-05-24"),
        ("Rafael", "M", "2019-09-02"),
    )
    family_names = ((
        "Almeida Santos", "Barbosa Lima", "Cardoso Oliveira", "Dias Ferreira", "Ferreira Souza",
        "Gomes Ribeiro", "Lima Martins", "Martins Silva", "Nascimento Costa", "Oliveira Rocha",
        "Pereira Alves", "Ribeiro Melo", "Santos Araújo", "Silva Moraes", "Souza Carvalho",
    ), (
        "Azevedo Lima", "Batista Santos", "Correia Alves", "Domingues Silva", "Esteves Rocha",
        "Freitas Melo", "Gonçalves Souza", "Henrique Costa", "Jesus Oliveira", "Lopes Martins",
        "Machado Ribeiro", "Nunes Ferreira", "Pinto Araújo", "Queiroz Moraes", "Vieira Carvalho",
    ))[polo_number - 1]
    responsible_names = ((
        "Juliana", "Camila", "Patrícia", "Renata", "Fernanda",
        "Aline", "Mônica", "Cristiane", "Vanessa", "Luciana",
        "Daniela", "Priscila", "Tatiane", "Simone", "Adriana",
    ), (
        "Mariana", "Carolina", "Elaine", "Rosana", "Sílvia",
        "Cláudia", "Andréia", "Fabiana", "Michele", "Sandra",
        "Elisângela", "Jaqueline", "Viviane", "Kátia", "Regina",
    ))[polo_number - 1]
    rows = []
    for index, ((first_name, sex, birth_date), family_name, responsible_name) in enumerate(zip(first_names, family_names, responsible_names), 1):
        transition_birthdays = {(1, 4): "2016-10-10", (1, 8): "2016-11-15", (2, 13): "2016-12-05"}
        birth_date = transition_birthdays.get((polo_number, index), birth_date)
        rows.append({
            "nome_crianca": f"{first_name} {family_name}".upper(),
            "sexo": sex,
            "data_nascimento": birth_date,
            "comum_congregacao": polo,
            "polo_participacao": polo,
            "nome_responsavel": f"{responsible_name} {family_name}".upper(),
            "celular_responsavel": f"(11) 9{polo_number}7{index:02d}-{(3100 + polo_number * 100 + index * 17):04d}",
            "tem_whatsapp": True,
            "cidade": "JANDIRA",
            "complemento": MARKER,
            "status": "Ativo",
        })
    return rows


def staff_for(polo, polo_number):
    roles = ("Coordenadora", "Monitora", "Monitora", "Monitora", "Monitora")
    names = ((
        "Marcia Regina de Oliveira", "Ana Paula Mendes", "Beatriz Gomes da Silva",
        "Carla Cristina Ribeiro", "Daniela Alves de Souza",
    ), (
        "Rosangela Maria Ferreira", "Amanda Santos Lima", "Bruna Martins Rocha",
        "Claudia Regina Nunes", "Debora Cristina Vieira",
    ))[polo_number - 1]
    return [{
        "nome_completo": name.upper(),
        "comum_congregacao": polo,
        "polo_auxilio": polo,
        "celular": f"(11) 9{polo_number}8{index:02d}-{(4200 + polo_number * 100 + index * 19):04d}",
        "email": f"{'.'.join(name.casefold().split()[:2])}@exemplo.com",
        "instrutor_atualmente": True,
        "afinidade_criancas": True,
        "de_acordo_voluntario": True,
        "autoriza_tratamento_dados": True,
        "cursos_conhecimentos": MARKER,
        "status": "Ativo",
        "role": role,
    } for index, (name, role) in enumerate(zip(names, roles), 1)]


class Command(BaseCommand):
    help = "Cria ou remove o lote temporario do treinamento de Musicalizacao em Jandira."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Remove somente o lote marcado de treinamento.")

    def handle(self, *args, **options):
        if options["delete"]:
            self._delete()
            return
        self._create()

    def _marked_rows(self, table, marker_field):
        response = requests.get(
            url(table), headers=headers(),
            params={"select": f"id,{marker_field}", marker_field: f"eq.{MARKER}"}, timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _delete(self, quiet=False):
        removed = {}
        for table, field in (("musicalizacao_criancas", "complemento"), ("musicalizacao_monitores", "cursos_conhecimentos")):
            existing = self._marked_rows(table, field)
            response = requests.delete(
                url(table), headers=headers("return=minimal"),
                params={field: f"eq.{MARKER}"}, timeout=30,
            )
            response.raise_for_status()
            removed[table] = len(existing)
        self._clear_cache()
        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f"Lote removido: {removed['musicalizacao_criancas']} criancas e "
                f"{removed['musicalizacao_monitores']} integrantes de equipe."
            ))

    def _create(self):
        existing_children = self._marked_rows("musicalizacao_criancas", "complemento")
        existing_staff = self._marked_rows("musicalizacao_monitores", "cursos_conhecimentos")
        if existing_children or existing_staff:
            raise CommandError(
                f"O lote {MARKER} ja existe ({len(existing_children)} criancas, {len(existing_staff)} integrantes). "
                "Use --delete antes de recriar."
            )

        children = []
        staff = []
        for polo_number, polo in enumerate(POLOS, 1):
            children.extend(children_for(polo, polo_number))
            staff.extend(staff_for(polo, polo_number))
        try:
            child_response = requests.post(
                url("musicalizacao_criancas"), headers=headers(), json=children, timeout=30,
            )
            child_response.raise_for_status()
            staff_response = requests.post(
                url("musicalizacao_monitores"), headers=headers(), json=staff, timeout=30,
            )
            staff_response.raise_for_status()
        except requests.RequestException as exc:
            self._delete(quiet=True)
            raise CommandError(f"Falha ao criar o lote; qualquer inclusao parcial foi removida: {exc}") from exc

        self._clear_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Lote criado: {len(children)} criancas e {len(staff)} integrantes de equipe em 2 polos."
        ))
        self.stdout.write(f"Para remover depois: python manage.py seed_jandira_training --delete")

    @staticmethod
    def _clear_cache():
        cache.delete("musicalizacao:dashboard:v7")
        cache.delete("musicalizacao:source:v7:criancas")
        cache.delete("musicalizacao:source:v7:instrutores")
