from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from database import get_db
from database.models import (
    MovieModel, GenreModel, ActorModel,
    LanguageModel, CountryModel
)
from schemas.movies import (
    MovieListResponseSchema, MovieDetailSchema,
    MovieCreateSchema, MovieUpdateSchema,
    MessageResponseSchema, MovieListItemSchema,
    CountrySchema, GenreSchema, ActorSchema, LanguageSchema,
    MovieStatus
)

router = APIRouter()


@router.get(
    "/",
    response_model=MovieListResponseSchema,
    responses={404: {"description": "No movies found"}}
)
async def get_movies(
        page: int = Query(1, ge=1),
        per_page: int = Query(10, ge=1, le=20),
        db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a paginated list of movies.
    """
    # Calculate offset
    offset = (page - 1) * per_page

    # Get total count
    count_stmt = select(func.count(MovieModel.id))
    total_result = await db.execute(count_stmt)
    total_items = total_result.scalar_one()

    if total_items == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found."
        )

    # Calculate total pages
    total_pages = (total_items + per_page - 1) // per_page

    # Check if page exceeds total pages
    if page > total_pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No movies found."
        )

    # Get movies for current page
    stmt = (
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    movies = result.scalars().all()

    # Build pagination links
    prev_page = None
    next_page = None

    if page > 1:
        prev_page = f"/theater/movies/?page={page - 1}&per_page={per_page}"

    if page < total_pages:
        next_page = f"/theater/movies/?page={page + 1}&per_page={per_page}"

    # Convert to schema
    movie_items = [
        MovieListItemSchema(
            id=movie.id,
            name=movie.name,
            date=movie.date,
            score=movie.score,
            overview=movie.overview
        )
        for movie in movies
    ]

    return MovieListResponseSchema(
        movies=movie_items,
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items
    )


@router.get(
    "/{movie_id}/",
    response_model=MovieDetailSchema,
    responses={404: {"description": "Movie not found"}}
)
async def get_movie_by_id(
        movie_id: int,
        db: AsyncSession = Depends(get_db)
):
    """
    Retrieve detailed information about a specific movie by ID.
    """
    # Use selectinload for collections instead of joinedload
    stmt = (
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            selectinload(MovieModel.genres),  # Use selectinload for collections
            selectinload(MovieModel.actors),  # Use selectinload for collections
            selectinload(MovieModel.languages),  # Use selectinload for collections
        )
        .where(MovieModel.id == movie_id)
    )

    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    # Convert to schema
    return MovieDetailSchema(
        id=movie.id,
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=MovieStatus(movie.status),  # Convert string to enum
        budget=float(movie.budget),
        revenue=movie.revenue,
        country=CountrySchema(
            id=movie.country.id,
            code=movie.country.code,
            name=movie.country.name
        ),
        genres=[
            GenreSchema(id=genre.id, name=genre.name)
            for genre in movie.genres
        ],
        actors=[
            ActorSchema(id=actor.id, name=actor.name)
            for actor in movie.actors
        ],
        languages=[
            LanguageSchema(id=lang.id, name=lang.name)
            for lang in movie.languages
        ]
    )


@router.post(
    "/",
    response_model=MovieDetailSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid input data"},
        409: {"description": "Movie already exists"}
    }
)
async def create_movie(
        movie_data: MovieCreateSchema,
        db: AsyncSession = Depends(get_db)
):
    """
    Create a new movie.
    """
    # Check for duplicate movie
    stmt = select(MovieModel).where(
        MovieModel.name == movie_data.name,
        MovieModel.date == movie_data.date
    )
    result = await db.execute(stmt)
    existing_movie = result.scalar_one_or_none()

    if existing_movie:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A movie with the name '{movie_data.name}' and release date '{movie_data.date}' already exists."
        )

    # Get or create country
    country_stmt = select(CountryModel).where(
        CountryModel.code == movie_data.country
    )
    country_result = await db.execute(country_stmt)
    country = country_result.scalar_one_or_none()

    if not country:
        country = CountryModel(code=movie_data.country, name=None)
        db.add(country)
        await db.flush()

    # Get or create genres
    genres = []
    for genre_name in movie_data.genres:
        genre_stmt = select(GenreModel).where(
            GenreModel.name == genre_name
        )
        genre_result = await db.execute(genre_stmt)
        genre = genre_result.scalar_one_or_none()

        if not genre:
            genre = GenreModel(name=genre_name)
            db.add(genre)
            await db.flush()
        genres.append(genre)

    # Get or create actors
    actors = []
    for actor_name in movie_data.actors:
        actor_stmt = select(ActorModel).where(
            ActorModel.name == actor_name
        )
        actor_result = await db.execute(actor_stmt)
        actor = actor_result.scalar_one_or_none()

        if not actor:
            actor = ActorModel(name=actor_name)
            db.add(actor)
            await db.flush()
        actors.append(actor)

    # Get or create languages
    languages = []
    for language_name in movie_data.languages:
        language_stmt = select(LanguageModel).where(
            LanguageModel.name == language_name
        )
        language_result = await db.execute(language_stmt)
        language = language_result.scalar_one_or_none()

        if not language:
            language = LanguageModel(name=language_name)
            db.add(language)
            await db.flush()
        languages.append(language)

    # Create movie
    movie = MovieModel(
        name=movie_data.name,
        date=movie_data.date,
        score=movie_data.score,
        overview=movie_data.overview,
        status=movie_data.status.value,  # Convert enum to string
        budget=movie_data.budget,
        revenue=movie_data.revenue,
        country_id=country.id,
        genres=genres,
        actors=actors,
        languages=languages
    )

    db.add(movie)
    await db.commit()
    await db.refresh(movie)

    # Load all relationships using selectinload for collections
    stmt = (
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
        )
        .where(MovieModel.id == movie.id)
    )
    result = await db.execute(stmt)
    movie = result.unique().scalar_one()  # Use unique() to handle joined results

    # Convert to schema
    return MovieDetailSchema(
        id=movie.id,
        name=movie.name,
        date=movie.date,
        score=movie.score,
        overview=movie.overview,
        status=MovieStatus(movie.status),  # Convert string to enum
        budget=float(movie.budget),
        revenue=movie.revenue,
        country=CountrySchema(
            id=movie.country.id,
            code=movie.country.code,
            name=movie.country.name
        ),
        genres=[
            GenreSchema(id=genre.id, name=genre.name)
            for genre in movie.genres
        ],
        actors=[
            ActorSchema(id=actor.id, name=actor.name)
            for actor in movie.actors
        ],
        languages=[
            LanguageSchema(id=lang.id, name=lang.name)
            for lang in movie.languages
        ]
    )


@router.delete(
    "/{movie_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Movie not found"}}
)
async def delete_movie(
        movie_id: int,
        db: AsyncSession = Depends(get_db)
):
    """
    Delete a movie by ID.
    """
    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    await db.delete(movie)
    await db.commit()

    # Return 204 No Content
    return None


@router.patch(
    "/{movie_id}/",
    response_model=MessageResponseSchema,
    responses={
        400: {"description": "Invalid input data"},
        404: {"description": "Movie not found"}
    }
)
async def update_movie(
        movie_id: int,
        update_data: MovieUpdateSchema,
        db: AsyncSession = Depends(get_db)
):
    """
    Update a movie by ID.
    """
    stmt = select(MovieModel).where(MovieModel.id == movie_id)
    result = await db.execute(stmt)
    movie = result.scalar_one_or_none()

    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movie with the given ID was not found."
        )

    # Update only provided fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field == 'status' and value:
            setattr(movie, field, value.value)  # Convert enum to string
        else:
            setattr(movie, field, value)

    await db.commit()
    await db.refresh(movie)

    return MessageResponseSchema(detail="Movie updated successfully.")
