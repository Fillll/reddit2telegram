FROM python:3

RUN mkdir /code/
WORKDIR /code/

ADD ./requirements.txt /code/requirements.txt
RUN pip install -r requirements.txt

ADD ./ /code/

ENTRYPOINT ["python", "main_app.py", "--sub"]
CMD ["unexpected"]